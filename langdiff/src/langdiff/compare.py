"""Where the language editions of one topic state different figures, or frame the same thing differently.

No LLM: three levels of vectors, all in MariaDB.
1. Article: the editions of a topic share a wikidata_id.
2. Passage: each part's nearest part in every other language over the whole corpus (HNSW on
   chunk.embedding), kept when the match is mutual and close. The counterpart may sit in another
   article: Finnish keeps "Talvisodan tausta" apart from "Talvisota".
3. Sentence: inside each passage pair, sentences that are each other's nearest. An exact join: a
   passage pair holds a few dozen sentence pairs, cheaper than index lookups.

Then, for sentence pairs clearly about the same thing:
- figures: numbers each side states differently (discrepancy.py);
- framing: how far apart the two sentences sit on a semantic axis, e.g. "stated as fact" vs
  "claimed or disputed". An axis is the difference of two groups of anchor sentences, written in all
  three languages so that the language itself cancels out; a sentence's position is one
  VEC_DISTANCE_COSINE against it.
"""

from functools import lru_cache

import numpy as np

from .discrepancy import anchored_conflicts, conflicts
from .embeddings import embed

LANGS = ("fi", "sv", "en")
PASSAGE_MAX = 0.40  # cosine distance for two parts to be about the same subject
FIGURES_MAX = 0.40  # sentence pairs compared for figures
FRAMING_MAX = 0.35  # sentence pairs compared for framing: stricter, it has no anchor like a number
FRAMING_MIN_Z = 1.2  # how many standard deviations apart two sentences must sit on an axis

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
        ("states it as fact", "presents it as uncertain or disputed"),
    ),
}


def unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


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


def axis_stats(cur) -> dict[str, dict[str, tuple[float, float]]]:
    """Per axis and language: mean and standard deviation of sentence positions. Languages sit at
    slightly different places on every axis; comparing against their own mean removes that."""
    if not _stats:
        for name, vector in axis_vectors().items():
            cur.execute(
                "SELECT lang, AVG(1 - VEC_DISTANCE_COSINE(embedding, %s)), STDDEV(1 - VEC_DISTANCE_COSINE(embedding, %s)) "
                "FROM sentence GROUP BY lang",
                (vector, vector),
            )
            _stats[name] = {lang: (mean, sd) for lang, mean, sd in cur.fetchall()}
    return _stats


def nearest_part(cur, lang: str, embedding: bytes):
    """(page_id, seq, distance) of the closest part in `lang`, anywhere in the corpus: HNSW."""
    cur.execute(
        "SELECT page_id, seq, VEC_DISTANCE_COSINE(embedding, %s) FROM chunk WHERE lang = %s "
        "ORDER BY VEC_DISTANCE_COSINE(embedding, %s) LIMIT 1",
        (embedding, lang, embedding),
    )
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
    return sorted(pairs)


def sentence_pairs(cur, pairs: list[tuple]) -> list[tuple]:
    """Mutual nearest sentences inside each passage pair, with their positions on every axis."""
    cur.execute(
        "CREATE TEMPORARY TABLE IF NOT EXISTS pair (a CHAR(2), apage INT UNSIGNED, aseq SMALLINT UNSIGNED, "
        "b CHAR(2), bpage INT UNSIGNED, bseq SMALLINT UNSIGNED)"
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
            SELECT r.a, r.apage, r.aseq, x.text, r.b, r.bpage, r.bseq, y.text, r.dist, {positions}
            FROM r
            JOIN sentence x ON x.lang = r.a AND x.page_id = r.apage AND x.seq = r.aseq AND x.n = r.an
            JOIN sentence y ON y.lang = r.b AND y.page_id = r.bpage AND y.seq = r.bseq AND y.n = r.bn
            WHERE r.ra = 1 AND r.rb = 1""",
        axes,
    )
    return cur.fetchall()


def findings(cur, wikidata_id: str, ensure_sentences) -> tuple[list[dict], list[dict]]:
    """(figures, framing) found between the editions of a topic, best first."""
    pairs = passage_pairs(cur, wikidata_id)
    for page in {(lang, page_id) for a, b, _ in pairs for lang, page_id, _ in (a, b)}:
        ensure_sentences(cur, *page)
    stats = axis_stats(cur)
    passages = {}
    if pairs:
        keys = {part for a, b, _ in pairs for part in (a, b)}
        cur.execute(
            "SELECT c.lang, c.page_id, c.seq, a.title, c.heading, c.text FROM chunk c JOIN article a USING (lang, page_id) "
            f"WHERE (c.lang, c.page_id, c.seq) IN ({', '.join(['(%s, %s, %s)'] * len(keys))})",
            [v for key in keys for v in key],
        )
        passages = {(lang, page_id, seq): {"lang": lang, "title": title, "heading": heading, "text": text}
                    for lang, page_id, seq, title, heading, text in cur.fetchall()}

    figures, framing = [], []
    for a, apage, aseq, atext, b, bpage, bseq, btext, dist, *pos in sentence_pairs(cur, pairs):
        sides = [{**passages[a, apage, aseq], "sentence": atext}, {**passages[b, bpage, bseq], "sentence": btext}]
        if dist <= FIGURES_MAX and (found := conflicts(atext, btext, dist)):
            figures.append({"distance": dist, "conflicts": found, "passages": sides})
        if dist <= FRAMING_MAX:
            best = None
            for i, (name, (_, _, ends)) in enumerate(AXES.items()):
                (ma, sa), (mb, sb) = stats[name][a], stats[name][b]
                dz = (pos[2 * i] - ma) / sa - (pos[2 * i + 1] - mb) / sb
                if abs(dz) >= FRAMING_MIN_Z and (not best or abs(dz) > abs(best["z"])):
                    # the side further toward the positive end "reads" like it; the other like the negative end
                    best = {"axis": name, "z": dz, "ends": ends}
            if best:
                framing.append({"distance": dist, **best, "passages": sides})
    figures.sort(key=lambda f: (-len(f["conflicts"]), f["distance"]))
    # Then whole passages, for figures the sentence pairing missed (a table row against a sentence).
    seen = {(f["passages"][0]["lang"], f["passages"][1]["lang"], *c) for f in figures for c in f["conflicts"]}
    more = []
    for a, b, dist in pairs:
        found = [c for c in anchored_conflicts(passages[a]["text"], passages[b]["text"]) if (a[0], b[0], *c) not in seen]
        if found:
            more.append({"distance": dist, "conflicts": found,
                         "passages": [{**passages[a], "sentence": None}, {**passages[b], "sentence": None}]})
    figures += sorted(more, key=lambda f: (-len(f["conflicts"]), f["distance"]))
    framing.sort(key=lambda f: -abs(f["z"]))
    return figures, framing
