"""Where the language editions of one topic frame the same thing differently.

No LLM: three levels of vectors, all in MariaDB.
1. Article: the editions of a topic share a wikidata_id.
2. Passage: each part's nearest part in every other language over the whole corpus (HNSW on
   chunk.embedding), kept when the match is mutual and close. The counterpart may sit in another
   article: Finnish keeps "Talvisodan tausta" apart from "Talvisota".
3. Sentence: inside each passage pair, sentences that are each other's nearest. An exact join: a
   passage pair holds a few dozen sentence pairs, cheaper than index lookups.

Matched sentences are then grouped across languages, closest pairs first, one sentence per language:
one group per fact, however many editions state it. Within a group:
- framing: each edition's position on a semantic axis, e.g. "stated as fact" vs "claimed or
  disputed", against the others' average. An axis is the difference of two groups of anchor
  sentences, written in all three languages so that the language itself cancels out; a sentence's
  position is one VEC_DISTANCE_COSINE against it. With three or more editions, the furthest is the
  outlier; with two, it is just their difference.

See docs/how-it-works.md.
"""

import threading
from collections.abc import Callable
from functools import lru_cache
from statistics import fmean

import numpy as np
import pymysql
import pymysql.cursors

from .db import LANGS
from .embeddings import embed_cached

ER_STATEMENT_TIMEOUT = 1969  # MariaDB: "Query execution was interrupted (max_statement_time exceeded)"

PASSAGE_MAX = 0.40  # cosine distance for two parts to be about the same subject
FRAMING_MAX = 0.35  # sentence pairs compared for framing: stricter, tone is compared on one statement
FRAMING_MIN_Z = 1.2  # how many standard deviations apart two sentences must sit on an axis
MIN_STATS_SENTENCES = 200  # fewer sentences in a language: use all languages' pooled mean and spread
MIN_EDITIONS = 2  # a comparison needs two editions
MIN_OUTLIER = 3  # with this many editions or more, the furthest is the outlier
BIG_GROUP = 8  # a statement this many editions make is a candidate whatever its tone
CONSENSUS_MAX = PASSAGE_MAX  # a sentence this close to a finding may state its subject; the LLM tells if it does
CONSENSUS_EDITIONS = 40  # other editions asked about a finding at most, the closest: one LLM call

# axis -> (anchors for the positive end, anchors for the negative end, how each end reads)
AXES = {
    "evaluation": (
        [
            "It was a great success and widely praised.",
            "Det var en stor framgång och fick mycket beröm.",
            "Se oli suuri menestys, ja sitä kehuttiin laajasti.",
            "A heroic and admirable achievement.",
            "En heroisk och beundransvärd bedrift.",
            "Sankarillinen ja ihailtava saavutus.",
        ],
        [
            "It was a disastrous failure and widely condemned.",
            "Det var ett katastrofalt misslyckande och fördömdes brett.",
            "Se oli tuhoisa epäonnistuminen, ja se tuomittiin laajasti.",
            "A brutal and shameful crime.",
            "Ett brutalt och skamligt brott.",
            "Julma ja häpeällinen rikos.",
        ],
        ("is more positive", "is more critical"),
    ),
    "certainty": (
        [
            "It is a well-documented fact.",
            "Det är ett väldokumenterat faktum.",
            "Se on hyvin dokumentoitu tosiasia.",
            "This is certain and confirmed by the records.",
            "Detta är säkert och bekräftat av arkiven.",
            "Tämä on varmaa ja asiakirjojen vahvistamaa.",
        ],
        [
            "This is only an unconfirmed claim and it is disputed.",
            "Detta är bara ett obekräftat påstående och det är omstritt.",
            "Tämä on vain vahvistamaton väite, ja se on kiistanalainen.",
            "According to some sources this allegedly happened.",
            "Enligt vissa källor ska detta ha hänt.",
            "Joidenkin lähteiden mukaan näin olisi tapahtunut.",
        ],
        ("states it more firmly as fact", "presents it as more uncertain or disputed"),
    ),
    # How something is described, whichever side: loaded, emotive wording vs neutral, matter-of-fact.
    "wording": (
        [
            "The ruthless aggressor savagely crushed the heroic defenders in a horrific bloodbath.",
            "Den hänsynslösa angriparen krossade brutalt de heroiska försvararna i ett fruktansvärt blodbad.",
            "Häikäilemätön hyökkääjä murskasi raa'asti sankarilliset puolustajat kauhistuttavassa verilöylyssä.",
            "This shameful betrayal was an outrageous and disgraceful act.",
            "Detta skamliga svek var en upprörande och vanhedrande handling.",
            "Tämä häpeällinen petos oli törkeä ja halveksittava teko.",
        ],
        [
            "The army attacked the defensive positions and both sides suffered casualties.",
            "Armén anföll försvarsställningarna och båda sidor led förluster.",
            "Armeija hyökkäsi puolustusasemiin, ja molemmat osapuolet kärsivät tappioita.",
            "The agreement was signed in 1940 and changed the border.",
            "Avtalet undertecknades 1940 och ändrade gränsen.",
            "Sopimus allekirjoitettiin vuonna 1940, ja se muutti rajaa.",
        ],
        ("uses more loaded, emotive wording", "uses more neutral, matter-of-fact wording"),
    ),
}


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def lang_order(lang: str) -> tuple[int, str]:
    """fi, sv, en first (matched over the whole corpus, see passage_pairs), then the rest alphabetically."""
    return (LANGS.index(lang), "") if lang in LANGS else (len(LANGS), lang)


@lru_cache
def axis_vectors() -> dict[str, bytes]:
    """Each axis as a VECTOR value: mean of its positive anchors minus mean of its negative ones."""
    out = {}
    for name, (pos, neg, _) in AXES.items():
        p, n = (unit(np.stack([np.frombuffer(v, "<f4") for v in embed_cached(group)])) for group in (pos, neg))
        out[name] = unit(p.mean(0) - n.mean(0)).astype("<f4").tobytes()
    return out


# shortcut: computed once per process over the sentences embedded so far (again when a topic brings
# languages not seen yet); at Wikipedia scale, keep these per-language statistics in a table
# refreshed after each bulk load.
_stats: dict[str, dict[str, tuple[float, float]]] = {}
_pooled: dict[str, tuple[float, float]] = {}
_seen: set[str] = set()  # languages present when _stats was computed
# Requests run on parallel threads: one computes, the others wait, so no request reads the statistics
# half-made (languages marked seen before every axis was computed: KeyError).
_stats_lock = threading.Lock()


def axis_stats(cur: pymysql.cursors.Cursor, langs: set[str]) -> dict[str, dict[str, tuple[float, float]]]:
    """Per axis and language: mean and standard deviation of sentence positions. Languages sit at
    slightly different places on every axis; comparing against their own mean removes that. A
    language with too few sentences for its own statistics gets all languages' pooled ones.
    """
    axes = axis_vectors()
    with _stats_lock:
        if not langs <= _seen:  # small languages never get their own entry: remember they were counted
            for name, vector in axes.items():
                position = "1 - VEC_DISTANCE_COSINE(embedding, %s)"
                cur.execute(
                    f"SELECT lang, COUNT(*), AVG({position}), STDDEV({position}) FROM sentence GROUP BY lang",
                    (vector, vector),
                )
                rows = cur.fetchall()
                _stats[name] = {lang: (mean, sd) for lang, n, mean, sd in rows if n >= MIN_STATS_SENTENCES}
                _seen.update(lang for lang, *_ in rows)
                cur.execute(f"SELECT AVG({position}), STDDEV({position}) FROM sentence", (vector, vector))
                _pooled[name] = cur.fetchone()
            _seen.update(langs)  # a language with no sentences yet must not trigger this on every request
    return {
        name: {lang: _stats[name][lang] if lang in _stats[name] else _pooled[name] for lang in langs} for name in axes
    }


HNSW_TIMEOUT = 2  # seconds; a lookup normally takes milliseconds


def nearest_part(cur: pymysql.cursors.Cursor, lang: str, embedding: bytes) -> tuple | None:
    """(page_id, seq, distance) of the closest part in `lang`, anywhere in the corpus: HNSW.

    MariaDB 12.3 can loop on a filtered HNSW search with LIMIT 1, growing memory until the server is
    killed (seen for one en passage of Urho Kekkonen searched in fi; LIMIT 10 and the exact search
    answer at once). So the index lookup is time-limited and falls back to the exact search.
    """
    query = (
        "SELECT page_id, seq, VEC_DISTANCE_COSINE(embedding, %s) FROM chunk {} WHERE lang = %s "
        "ORDER BY VEC_DISTANCE_COSINE(embedding, %s) LIMIT 1"
    )
    try:
        cur.execute(
            f"SET STATEMENT max_statement_time={HNSW_TIMEOUT} FOR " + query.format(""), (embedding, lang, embedding)
        )
    except pymysql.err.OperationalError as e:
        if e.args[0] != ER_STATEMENT_TIMEOUT:
            raise
        # shortcut: a full scan of the language's parts; fine per lookup, slow if it happens often at scale
        cur.execute(query.format("IGNORE INDEX (embedding)"), (embedding, lang, embedding))
    return cur.fetchone()


def passage_pairs(cur: pymysql.cursors.Cursor, wikidata_id: str) -> list[tuple]:
    """Mutual nearest parts in two languages, closer than PASSAGE_MAX: ((lang, page_id, seq) × 2, distance)."""
    cur.execute(
        "SELECT c.lang, c.page_id, c.seq, c.embedding FROM chunk c JOIN article a USING (lang, page_id) "
        "WHERE a.wikidata_id = %s",
        (wikidata_id,),
    )
    own = {(lang, page_id, seq): emb for lang, page_id, seq, emb in cur.fetchall()}
    nearest: dict[tuple, tuple] = {}  # (part, other lang) -> (counterpart, distance)

    def lookup(part: tuple, lang: str, emb: bytes) -> tuple | None:
        if (part, lang) not in nearest and (hit := nearest_part(cur, lang, emb)):
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


def sentence_pairs(cur: pymysql.cursors.Cursor, pairs: list[tuple]) -> list[tuple]:
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
    """Groups of items (sentences or passages) from matched pairs closer than max_dist: (items,
    largest distance of a pair inside). A group holds one item per language: pairs join their groups
    closest first, and only when the two groups have no language in common, so a chain that would
    reach a second sentence of one language stops there instead of breaking the group up. A pair
    left between two groups is kept as a group of its own, after the groups: its two sentences
    still match. Merging such pairs around a shared sentence before judging lost findings
    (docs/experiments/2026-11-bias-framing.md); app.merge_shared() merges them after.
    """
    parent: dict = {}
    langs: dict = {}  # group root -> its languages

    def find(x: tuple) -> tuple:
        root = x
        while parent.setdefault(root, root) != root:
            root = parent[root]
        while x != root:  # path compression: chains stay short (66 editions took 12 s without it)
            parent[x], x = root, parent[x]
        return root

    kept = sorted((e for e in edges if e[2] <= max_dist), key=lambda e: (e[2], e[0], e[1]))
    for a, b, _ in kept:
        ra, rb = find(a), find(b)
        if ra != rb and not (la := langs.get(ra, {a[0]})) & (lb := langs.get(rb, {b[0]})):
            parent[ra] = rb
            langs[rb] = la | lb
    inside: dict = {}
    between = []
    for a, b, d in kept:
        if (root := find(a)) == find(b):
            members, dist = inside.get(root, (set(), 0.0))
            inside[root] = (members | {a, b}, max(dist, d))
        else:
            between.append((sorted([a, b], key=lambda item: lang_order(item[0])), d))
    return [
        (sorted(members, key=lambda item: lang_order(item[0])), dist) for members, dist in inside.values()
    ] + between


def spread(ids: list[tuple], distance: dict[frozenset, float]) -> list[tuple]:
    """A group's items, most different first: the farthest matched pair, then each next item the one
    farthest from those chosen (by its matched pairs with them), the rest in their order. The first
    SHOWN are what a card shows and the decision model judges: in a 24-edition group, language order
    showed three that agreed.
    """
    known = [(d, sorted(p, key=ids.index)) for p, d in distance.items() if p <= set(ids)]
    if not known:
        return ids
    chosen = max(known)[1]
    while len(chosen) < len(ids):
        gaps = {
            i: min(ds)
            for i in ids
            if i not in chosen and (ds := [distance[p] for c in chosen if (p := frozenset((i, c))) in distance])
        }
        if not gaps:
            break
        chosen.append(max(gaps, key=lambda i: (gaps[i], -ids.index(i))))
    return chosen + [i for i in ids if i not in chosen]


def differences(
    cur: pymysql.cursors.Cursor,
    wikidata_id: str,
    ensure_sentences: Callable[[pymysql.cursors.Cursor, list[tuple[str, int]]], None],
    langs: set[str],
) -> list[dict]:
    """What the editions of a topic (those in `langs`) state differently, best first ({"kind": "framing"},
    by deviation): the axis and its `ends`, the edition `lang` furthest from the others' average by
    `deviation` σ, every edition's `deviations` on that axis, `outlier` (three or more editions) and
    `distance` (the largest cosine distance of a matched pair in the group). Each has members, one per
    language: the passage, its position (page_id, seq) and the sentence (n, sentence).
    """
    # Matching is mutual per language pair, so leaving editions out does not change the other pairs.
    pairs = [p for p in passage_pairs(cur, wikidata_id) if p[0][0] in langs and p[1][0] in langs]
    ensure_sentences(cur, sorted({(lang, page_id) for a, b, _ in pairs for lang, page_id, _ in (a, b)}))
    stats = axis_stats(cur, {item[0] for a, b, _ in pairs for item in (a, b)})
    passages = {}
    if pairs:
        keys = {part for a, b, _ in pairs for part in (a, b)}
        cur.execute(
            "SELECT c.lang, c.page_id, c.seq, a.title, c.heading, c.text "
            "FROM chunk c JOIN article a USING (lang, page_id) "
            f"WHERE (c.lang, c.page_id, c.seq) IN ({', '.join(['(%s, %s, %s)'] * len(keys))})",
            [v for key in keys for v in key],
        )
        passages = {
            (lang, page_id, seq): {
                "lang": lang,
                "title": title,
                "heading": heading,
                "text": text,
                "page_id": page_id,
                "seq": seq,
            }
            for lang, page_id, seq, title, heading, text in cur.fetchall()
        }

    sentence: dict[tuple, tuple[str, list[float]]] = {}  # (lang, page_id, seq, n) -> (text, axis positions)
    edges = []
    for a, apage, aseq, an, atext, b, bpage, bseq, bn, btext, dist, *pos in sentence_pairs(cur, pairs):
        sa, sb = (a, apage, aseq, an), (b, bpage, bseq, bn)
        sentence[sa], sentence[sb] = (atext, pos[0::2]), (btext, pos[1::2])
        edges.append((sa, sb, dist))

    def member(i: tuple) -> dict:  # a sentence (lang, page_id, seq, n)
        return {**passages[i[:3]], "n": i[3], "sentence": sentence[i][0]}

    distance = {frozenset((a, b)): d for a, b, d in edges}
    framing: list[dict] = []
    for ids, dist in groups(edges, FRAMING_MAX):
        best: dict | None = None
        for k, (name, (_, _, ends)) in enumerate(AXES.items()):
            z = {i[0]: (sentence[i][1][k] - stats[name][i[0]][0]) / stats[name][i[0]][1] for i in ids}
            # how far each edition sits from the others' average: with two, just their difference
            deviations = {lang: zl - fmean(v for other, v in z.items() if other != lang) for lang, zl in z.items()}
            for lang, deviation in deviations.items():
                if not best or abs(deviation) > abs(best["deviation"]):
                    best = {
                        "axis": name,
                        "ends": ends,
                        "lang": lang,
                        "deviation": deviation,
                        "deviations": {other: round(d, 2) for other, d in deviations.items()},
                    }
        # A statement many editions make is a core one: a candidate whatever its tone, which averaging
        # over many editions flattens (Mainila's lead, 24 editions: at most 1.12σ).
        if best and (abs(best["deviation"]) >= FRAMING_MIN_Z or len(ids) >= BIG_GROUP):
            framing.append(
                {
                    "kind": "framing",
                    "distance": dist,
                    **best,
                    "outlier": len(ids) >= MIN_OUTLIER,
                    "members": [member(i) for i in spread(ids, distance)],
                }
            )
    framing.sort(key=lambda f: -abs(f["deviation"]))
    return framing


def nearest_elsewhere(cur: pymysql.cursors.Cursor, quotes: list[tuple]) -> list[dict]:
    """For a finding's quotes (lang, page_id, seq, n): in each other edition of their topic, the sentence
    closest to their mean, if within CONSENSUS_MAX ({"lang", "sentence"}, closest first, CONSENSUS_EDITIONS at
    most). Exact search over the topic's sentences: those of passages a comparison matched, already split.
    """
    places = ", ".join(["(%s, %s, %s, %s)"] * len(quotes))
    cur.execute(
        f"SELECT embedding FROM sentence WHERE (lang, page_id, seq, n) IN ({places})", [v for q in quotes for v in q]
    )
    vectors = [np.frombuffer(e, "<f4") for (e,) in cur.fetchall()]
    if not vectors:
        return []
    mean = unit(unit(np.stack(vectors)).mean(0)).astype("<f4").tobytes()
    cur.execute(
        f"""WITH d AS (
              SELECT s.lang, s.text, VEC_DISTANCE_COSINE(s.embedding, %s) AS dist
              FROM sentence s JOIN article a USING (lang, page_id)
              WHERE a.wikidata_id IN (SELECT wikidata_id FROM article
                                      WHERE (lang, page_id) IN ({", ".join(["(%s, %s)"] * len(quotes))}))
                AND s.lang NOT IN ({", ".join(["%s"] * len(quotes))})),
            r AS (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY lang ORDER BY dist) AS rk FROM d)
            SELECT lang, text FROM r WHERE rk = 1 AND dist <= %s ORDER BY dist LIMIT %s""",
        [mean, *[v for q in quotes for v in q[:2]], *[q[0] for q in quotes], CONSENSUS_MAX, CONSENSUS_EDITIONS],
    )
    return [{"lang": lang, "sentence": text} for lang, text in cur.fetchall()]
