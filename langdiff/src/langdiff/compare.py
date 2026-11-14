"""Where the language editions of one topic frame the same thing differently, or state very different figures.

No LLM: three levels of vectors, all in MariaDB.
1. Article: the editions of a topic share a wikidata_id.
2. Passage: each part's nearest part in every other language over the whole corpus (HNSW on
   chunk.embedding), kept when the match is mutual and close. The counterpart may sit in another
   article: Finnish keeps "Talvisodan tausta" apart from "Talvisota".
3. Sentence: inside each passage pair, sentences that are each other's nearest. An exact join: a
   passage pair holds a few dozen sentence pairs, cheaper than index lookups.

Matched sentences are then grouped across languages: pairs that connect (fi-sv, sv-en, fi-en) form
one group per fact, one sentence per language. Within a group:
- framing: each edition's position on a semantic axis, e.g. "stated as fact" vs "claimed or
  disputed", against the others' average. An axis is the difference of two groups of anchor
  sentences, written in all three languages so that the language itself cancels out; a sentence's
  position is one VEC_DISTANCE_COSINE against it. With three or more editions, the furthest is the
  outlier; with two, it is just their difference.
- values: a figure stated very differently (discrepancy.py, at least 20% apart); with a majority,
  the editions against it are outliers ("126 875 (fi) vs 167,976 (en)").

See docs/how-it-works.md.
"""

from functools import lru_cache
from statistics import fmean

import numpy as np
import pymysql

from .db import LANGS
from .discrepancy import anchored_conflicts, conflicts, figure_slots, value
from .embeddings import embed

ER_STATEMENT_TIMEOUT = 1969  # MariaDB: "Query execution was interrupted (max_statement_time exceeded)"

PASSAGE_MAX = 0.40  # cosine distance for two parts to be about the same subject
VALUES_MAX = 0.40  # sentence pairs compared for values
FRAMING_MAX = 0.35  # sentence pairs compared for framing: stricter, it has no anchor like a number
FRAMING_MIN_Z = 1.2  # how many standard deviations apart two sentences must sit on an axis
MIN_STATS_SENTENCES = 200  # fewer sentences in a language: use all languages' pooled mean and spread

# axis -> (anchors for the positive end, anchors for the negative end, how each end reads)
AXES = {
    "evaluation": (
        ["It was a great success and widely praised.", "Det var en stor framgång och fick mycket beröm.",
         "Se oli suuri menestys, ja sitä kehuttiin laajasti.", "A heroic and admirable achievement.",
         "En heroisk och beundransvärd bedrift.", "Sankarillinen ja ihailtava saavutus."],
        ["It was a disastrous failure and widely condemned.", "Det var ett katastrofalt misslyckande och fördömdes brett.",
         "Se oli tuhoisa epäonnistuminen, ja se tuomittiin laajasti.", "A brutal and shameful crime.",
         "Ett brutalt och skamligt brott.", "Julma ja häpeällinen rikos."],
        ("is more positive", "is more critical"),
    ),
    "certainty": (
        ["It is a well-documented fact.", "Det är ett väldokumenterat faktum.", "Se on hyvin dokumentoitu tosiasia.",
         "This is certain and confirmed by the records.", "Detta är säkert och bekräftat av arkiven.",
         "Tämä on varmaa ja asiakirjojen vahvistamaa."],
        ["This is only an unconfirmed claim and it is disputed.", "Detta är bara ett obekräftat påstående och det är omstritt.",
         "Tämä on vain vahvistamaton väite, ja se on kiistanalainen.", "According to some sources this allegedly happened.",
         "Enligt vissa källor ska detta ha hänt.", "Joidenkin lähteiden mukaan näin olisi tapahtunut."],
        ("states it more firmly as fact", "presents it as more uncertain or disputed"),
    ),
}


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def lang_order(lang: str) -> tuple[int, str]:
    """fi, sv, en first (the dataset's languages), then the rest alphabetically."""
    return (LANGS.index(lang), "") if lang in LANGS else (len(LANGS), lang)


@lru_cache
def axis_vectors() -> dict[str, bytes]:
    """Each axis as a VECTOR value: mean of its positive anchors minus mean of its negative ones."""
    out = {}
    for name, (pos, neg, _) in AXES.items():
        p, n = (unit(np.stack([np.frombuffer(v, "<f4") for v in embed(group)])) for group in (pos, neg))
        out[name] = unit(p.mean(0) - n.mean(0)).astype("<f4").tobytes()
    return out


# shortcut: computed once per process over the sentences embedded so far; at Wikipedia scale,
# keep these per-language statistics in a table refreshed after each bulk load.
_stats: dict[str, dict[str, tuple[float, float]]] = {}


def axis_stats(cur, langs: set[str]) -> dict[str, dict[str, tuple[float, float]]]:
    """Per axis and language: mean and standard deviation of sentence positions. Languages sit at
    slightly different places on every axis; comparing against their own mean removes that. A
    language with too few sentences for its own statistics gets all languages' pooled ones."""
    axes = axis_vectors()
    pooled = {}
    if any(lang not in _stats.get(name, {}) for name in axes for lang in langs):
        for name, vector in axes.items():
            position = "1 - VEC_DISTANCE_COSINE(embedding, %s)"
            cur.execute(
                f"SELECT lang, COUNT(*), AVG({position}), STDDEV({position}) FROM sentence GROUP BY lang",
                (vector, vector),
            )
            _stats[name] = {lang: (mean, sd) for lang, n, mean, sd in cur.fetchall() if n >= MIN_STATS_SENTENCES}
            cur.execute(f"SELECT AVG({position}), STDDEV({position}) FROM sentence", (vector, vector))
            pooled[name] = cur.fetchone()
    return {
        name: {lang: _stats[name][lang] if lang in _stats[name] else pooled[name] for lang in langs}
        for name in axes
    }


HNSW_TIMEOUT = 2  # seconds; a lookup normally takes milliseconds


def nearest_part(cur, lang: str, embedding: bytes):
    """(page_id, seq, distance) of the closest part in `lang`, anywhere in the corpus: HNSW.

    MariaDB 12.3 can loop on a filtered HNSW search with LIMIT 1, growing memory until the server is
    killed (seen for one en passage of Urho Kekkonen searched in fi; LIMIT 10 and the exact search
    answer at once). So the index lookup is time-limited and falls back to the exact search."""
    query = ("SELECT page_id, seq, VEC_DISTANCE_COSINE(embedding, %s) FROM chunk {} WHERE lang = %s "
             "ORDER BY VEC_DISTANCE_COSINE(embedding, %s) LIMIT 1")
    try:
        cur.execute(f"SET STATEMENT max_statement_time={HNSW_TIMEOUT} FOR " + query.format(""), (embedding, lang, embedding))
    except pymysql.err.OperationalError as e:
        if e.args[0] != ER_STATEMENT_TIMEOUT:
            raise
        # shortcut: a full scan of the language's parts; fine per lookup, slow if it happens often at scale
        cur.execute(query.format("IGNORE INDEX (embedding)"), (embedding, lang, embedding))
    return cur.fetchone()


def passage_pairs(cur, wikidata_id: str) -> list[tuple]:
    """Mutual nearest parts in two languages, closer than PASSAGE_MAX: ((lang, page_id, seq) × 2, distance)."""
    cur.execute(
        "SELECT c.lang, c.page_id, c.seq, c.embedding FROM chunk c JOIN article a USING (lang, page_id) "
        "WHERE a.wikidata_id = %s",
        (wikidata_id,),
    )
    own = {(lang, page_id, seq): emb for lang, page_id, seq, emb in cur.fetchall()}
    nearest: dict[tuple, tuple] = {}  # (part, other lang) -> (counterpart, distance)

    def lookup(part, lang, emb):
        if (part, lang) not in nearest:
            if hit := nearest_part(cur, lang, emb):
                nearest[part, lang] = ((lang, hit[0], hit[1]), hit[2])
        return nearest.get((part, lang))

    pairs = set()
    for part, emb in own.items():
        if part[0] not in LANGS:
            continue
        for lang in LANGS:
            if lang == part[0] or not (hit := lookup(part, lang, emb)) or hit[1] > PASSAGE_MAX:
                continue
            other, dist = hit
            if other not in own:  # a counterpart in another article: look it up from its side too
                cur.execute("SELECT embedding FROM chunk WHERE lang = %s AND page_id = %s AND seq = %s", other)
                own_emb = cur.fetchone()[0]
            else:
                own_emb = own[other]
            back = lookup(other, part[0], own_emb)
            if back and back[0] == part:
                pairs.add((min(part, other), max(part, other), dist))
    # HNSW on a rare language has to filter almost the whole index: outside fi/sv/en, look for the
    # counterpart inside the topic, by an exact join (only this topic has parts in most languages).
    cur.execute(
        f"""WITH t AS (SELECT c.lang, c.page_id, c.seq, c.embedding FROM chunk c JOIN article a USING (lang, page_id)
                      WHERE a.wikidata_id = %s),
            d AS (SELECT x.lang AS a, x.page_id AS apage, x.seq AS aseq, y.lang AS b, y.page_id AS bpage, y.seq AS bseq,
                         VEC_DISTANCE_COSINE(x.embedding, y.embedding) AS dist
                  FROM t x JOIN t y ON x.lang < y.lang
                  WHERE NOT (x.lang IN {LANGS} AND y.lang IN {LANGS})),
            r AS (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY a, apage, aseq, b ORDER BY dist) AS ra,
                              ROW_NUMBER() OVER (PARTITION BY b, bpage, bseq, a ORDER BY dist) AS rb FROM d)
            SELECT a, apage, aseq, b, bpage, bseq, dist FROM r WHERE ra = 1 AND rb = 1 AND dist <= %s""",
        (wikidata_id, PASSAGE_MAX),
    )
    pairs |= {((a, apage, aseq), (b, bpage, bseq), dist) for a, apage, aseq, b, bpage, bseq, dist in cur.fetchall()}
    return sorted(pairs)


def sentence_pairs(cur, pairs: list[tuple]) -> list[tuple]:
    """Mutual nearest sentences inside each passage pair, with their positions on every axis."""
    cur.execute(
        "CREATE TEMPORARY TABLE IF NOT EXISTS pair (a VARCHAR(12), apage INT UNSIGNED, aseq SMALLINT UNSIGNED, "
        "b VARCHAR(12), bpage INT UNSIGNED, bseq SMALLINT UNSIGNED)"
    )
    cur.execute("TRUNCATE pair")
    cur.executemany("INSERT INTO pair VALUES (%s, %s, %s, %s, %s, %s)", [(*a, *b) for a, b, _ in pairs])
    axes = axis_vectors()
    positions = ", ".join(
        f"1 - VEC_DISTANCE_COSINE(x.embedding, %({name})s), 1 - VEC_DISTANCE_COSINE(y.embedding, %({name})s)"
        for name in axes
    )
    cur.execute(
        f"""WITH d AS (
              SELECT p.a, p.apage, p.aseq, x.n AS an, p.b, p.bpage, p.bseq, y.n AS bn,
                     VEC_DISTANCE_COSINE(x.embedding, y.embedding) AS dist
              FROM pair p
              JOIN sentence x ON x.lang = p.a AND x.page_id = p.apage AND x.seq = p.aseq
              JOIN sentence y ON y.lang = p.b AND y.page_id = p.bpage AND y.seq = p.bseq),
            r AS (
              SELECT d.*,
                     ROW_NUMBER() OVER (PARTITION BY a, apage, aseq, an, b, bpage, bseq ORDER BY dist) AS ra,
                     ROW_NUMBER() OVER (PARTITION BY b, bpage, bseq, bn, a, apage, aseq ORDER BY dist) AS rb
              FROM d)
            SELECT r.a, r.apage, r.aseq, r.an, x.text, r.b, r.bpage, r.bseq, r.bn, y.text, r.dist, {positions}
            FROM r
            JOIN sentence x ON x.lang = r.a AND x.page_id = r.apage AND x.seq = r.aseq AND x.n = r.an
            JOIN sentence y ON y.lang = r.b AND y.page_id = r.bpage AND y.seq = r.bseq AND y.n = r.bn
            WHERE r.ra = 1 AND r.rb = 1""",
        axes,
    )
    return cur.fetchall()


def groups(edges: list[tuple], max_dist: float) -> list[tuple[list, float]]:
    """Connected groups of items (sentences or passages) from matched pairs closer than max_dist:
    (items, largest distance inside). A group holds one item per language; a chain that reaches two
    items of one language falls back to its pairs."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    kept = [(a, b, d) for a, b, d in edges if d <= max_dist]
    for a, b, _ in kept:
        parent[find(a)] = find(b)
    components: dict = {}
    for a, b, d in kept:
        components.setdefault(find(a), []).append((a, b, d))
    out = []
    for pairs in components.values():
        members = {item for a, b, _ in pairs for item in (a, b)}
        if len({item[0] for item in members}) == len(members):
            out.append((sorted(members, key=lambda item: lang_order(item[0])), max(d for _, _, d in pairs)))
        else:
            out += [([a, b], d) for a, b, d in pairs]
    return out


def differences(cur, wikidata_id: str, ensure_sentences) -> list[dict]:
    """What the editions of a topic state differently, best first: values ({"kind": "value"}), then
    framing ({"kind": "framing"}). Each has members, one per language: the passage, its position
    (page_id, seq) and the sentence (n, sentence) or None when whole passages were compared.

    Matched sentences are grouped across languages (fi-sv, fi-en, sv-en pairs that connect form one
    group per fact); within a group, the edition that disagrees with the others is the outlier.
    """
    pairs = passage_pairs(cur, wikidata_id)
    ensure_sentences(cur, sorted({(lang, page_id) for a, b, _ in pairs for lang, page_id, _ in (a, b)}))
    stats = axis_stats(cur, {item[0] for a, b, _ in pairs for item in (a, b)})
    passages = {}
    if pairs:
        keys = {part for a, b, _ in pairs for part in (a, b)}
        cur.execute(
            "SELECT c.lang, c.page_id, c.seq, a.title, c.heading, c.text FROM chunk c JOIN article a USING (lang, page_id) "
            f"WHERE (c.lang, c.page_id, c.seq) IN ({', '.join(['(%s, %s, %s)'] * len(keys))})",
            [v for key in keys for v in key],
        )
        passages = {(lang, page_id, seq): {"lang": lang, "title": title, "heading": heading, "text": text,
                                           "page_id": page_id, "seq": seq}
                    for lang, page_id, seq, title, heading, text in cur.fetchall()}

    sentence: dict[tuple, tuple[str, list[float]]] = {}  # (lang, page_id, seq, n) -> (text, axis positions)
    edges = []
    for a, apage, aseq, an, atext, b, bpage, bseq, bn, btext, dist, *pos in sentence_pairs(cur, pairs):
        sa, sb = (a, apage, aseq, an), (b, bpage, bseq, bn)
        sentence[sa], sentence[sb] = (atext, pos[0::2]), (btext, pos[1::2])
        edges.append((sa, sb, dist))

    def member(i):  # a sentence (lang, page_id, seq, n) or a whole passage (lang, page_id, seq)
        return {**passages[i[:3]], "n": i[3], "sentence": sentence[i][0]} if len(i) == 4 \
            else {**passages[i], "n": None, "sentence": None}

    def change(slots):  # the largest relative difference among a finding's figures
        return max(1 - min(vs) / max(vs) for s in slots if (vs := [value(w) for w in s["values"].values()]))

    values = []
    for ids, dist in groups(edges, VALUES_MAX):
        text = {i[0]: sentence[i][0] for i in ids}
        if slots := figure_slots(text, lambda a, b: conflicts(text[a], text[b])):
            values.append({"kind": "value", "distance": dist, "slots": slots, "change": change(slots),
                           "members": [member(i) for i in ids]})
    # Then whole passages, for figures the sentence matching missed (a table row against a sentence).
    seen = {(lang, value(w)) for f in values for s in f["slots"] for lang, w in s["values"].items()}
    for ids, dist in groups(pairs, PASSAGE_MAX):
        text = {i[0]: passages[i]["text"] for i in ids}
        slots = [s for s in figure_slots(text, lambda a, b: anchored_conflicts(text[a], text[b]))
                 if not {(lang, value(w)) for lang, w in s["values"].items()} <= seen]
        if slots:
            values.append({"kind": "value", "distance": dist, "slots": slots, "change": change(slots),
                           "members": [member(i) for i in ids]})
    values.sort(key=lambda f: -f["change"])

    framing = []
    for ids, dist in groups(edges, FRAMING_MAX):
        best = None
        for k, (name, (_, _, ends)) in enumerate(AXES.items()):
            z = {i[0]: (sentence[i][1][k] - stats[name][i[0]][0]) / stats[name][i[0]][1] for i in ids}
            for lang, zl in z.items():
                # how far this edition sits from the others' average: with two, just their difference
                deviation = zl - fmean(v for other, v in z.items() if other != lang)
                if abs(deviation) >= FRAMING_MIN_Z and (not best or abs(deviation) > abs(best["deviation"])):
                    best = {"axis": name, "ends": ends, "lang": lang, "deviation": deviation}
        if best:
            framing.append({"kind": "framing", "distance": dist, **best, "outlier": len(ids) >= 3,
                            "members": [member(i) for i in ids]})
    framing.sort(key=lambda f: -abs(f["deviation"]))
    return values + framing
