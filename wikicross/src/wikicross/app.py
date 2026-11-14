"""API: where the Latin- and Cyrillic-script Wikipedia editions of one topic frame things differently or contradict each other."""

import hashlib
import json
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import compare, embed_gpu, wiki
from .compare import differences
from .db import SCHEMA, connect, widen_lang
from .embeddings import embed
from .llm import chat

MIN_CHARS = 300  # merge paragraphs until a part is at least this long: tiny parts embed noisily
TARGETS = {"en": "English"}  # languages the UI can translate into
# The comparison code and models: cached differences computed by others are not reused (diff_cache.state).
CODE = hashlib.sha256(b"".join(Path(m.__file__).read_bytes() for m in (compare, embed_gpu))).hexdigest()
# Sections that are lists of sources and links, not content; they always "differ". fi, sv, en.
SKIP = re.compile(
    r"\b(lähteet|viitteet|kirjallisuutta|aiheesta muualla|katso myös|huomautukset|"
    r"källor|fotnoter|noter|referenser|litteratur|externa länkar|se även|vidare läsning|"
    r"references|notes|sources|bibliography|cited|citations|further reading|external links|see also)\b",
    re.IGNORECASE,
)
# "Main article: X" lines: navigation, not content.
HATNOTE = re.compile(r"^(pääartikkelit?|huvudartikl(ar|el)|main articles?|further information|see also)\s*:", re.IGNORECASE)


@asynccontextmanager
async def lifespan(_app):
    with connect() as conn, conn.cursor() as cur:  # tables added after the data was loaded
        for stmt in SCHEMA:
            cur.execute(stmt)
        widen_lang(cur)
    yield


app = FastAPI(title="WikiCross", lifespan=lifespan)


def split(text: str) -> list[tuple[str, str]]:
    """Markdown -> [(heading, part)]: paragraphs (lines) merged up to MIN_CHARS, never across a heading."""
    parts: list[tuple[str, str]] = []
    heading, buf, skip_level = "", [], 0

    def flush():
        if buf:
            parts.append((heading, "\n".join(buf)))
            buf.clear()

    for line in text.splitlines():
        if m := re.match(r"(#+)\s+(.*)", line):
            flush()
            level, heading = len(m.group(1)), m.group(2).strip()[:500]
            if skip_level and level <= skip_level:
                skip_level = 0
            if not skip_level and SKIP.search(heading):
                skip_level = level
        elif line.strip() and not skip_level and not HATNOTE.match(line.strip()):
            buf.append(line.strip())
            if sum(map(len, buf)) >= MIN_CHARS:
                flush()
    flush()
    return parts


def _in(keys: list[tuple]) -> str:
    """`IN (...)` placeholders for a list of tuples."""
    return ", ".join(["(" + ", ".join(["%s"] * len(keys[0])) + ")"] * len(keys))


def ensure_chunks(cur, articles: list[tuple[str, int, str]]) -> None:
    """Split and embed the articles (lang, page_id, text) that have no parts yet: one embed() call."""
    if not articles:
        return
    keys = [(lang, page_id) for lang, page_id, _ in articles]
    cur.execute(f"SELECT DISTINCT lang, page_id FROM chunk WHERE (lang, page_id) IN ({_in(keys)})",
                [v for k in keys for v in k])
    done = set(cur.fetchall())
    rows = [(lang, page_id, i, h, t) for lang, page_id, text in articles if (lang, page_id) not in done
            for i, (h, t) in enumerate(split(text))]
    if not rows:
        return
    vectors = embed([f"{h}\n\n{t}" if h else t for *_, h, t in rows])
    cur.connection.begin()  # an interrupted run leaves all of an article's parts or none
    cur.executemany("INSERT IGNORE INTO chunk VALUES (%s, %s, %s, %s, %s, %s)",
                    [(*row, v) for row, v in zip(rows, vectors)])
    cur.connection.commit()


# A sentence ends at . ! ? followed by an uppercase letter of any alphabet, a quote or a bracket. Not
# before a digit or a lowercase letter: "(k. 1985)", "3. syyskuuta", "z. B. der" stay whole; a sentence
# starting with a year joins the one before, which is harmless.
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=\S)")
OPENERS = "\"“”«„("
MIN_SENTENCE = 30  # shorter pieces ("Ks. myös.") join a neighbour in the same line


def sentences(part: str) -> list[str]:
    """A part's sentences; table rows and list items count as one sentence each."""
    out: list[str] = []
    for line in part.splitlines():
        line = line.strip()
        if not line or (line.startswith("|") and set(line) <= set("|-: ")):
            continue  # blank, or a table separator row
        if line.startswith(("|", "- ")):
            out.append(line)
            continue
        mine, buf = [], ""
        pieces, start = [], 0
        for m in SENTENCE_BREAK.finditer(line):
            if line[m.end()] in OPENERS or line[m.end()].isupper():
                pieces.append(line[start:m.start()].strip())
                start = m.end()
        pieces.append(line[start:].strip())
        for piece in pieces:
            buf = f"{buf} {piece}".strip()
            if len(buf) >= MIN_SENTENCE:
                mine.append(buf)
                buf = ""
        if buf and mine:
            mine[-1] += " " + buf
        elif buf:
            mine.append(buf)
        out += mine
    return out


def ensure_sentences(cur, pages: list[tuple[str, int]]) -> None:
    """Embed the sentences of the pages' parts (parts must exist) that have none yet: one embed() call."""
    if not pages:
        return
    cur.execute(f"SELECT DISTINCT lang, page_id FROM sentence WHERE (lang, page_id) IN ({_in(pages)})",
                [v for k in pages for v in k])
    missing = sorted(set(map(tuple, pages)) - set(cur.fetchall()))
    if not missing:
        return
    cur.execute(
        f"SELECT lang, page_id, seq, text FROM chunk WHERE (lang, page_id) IN ({_in(missing)}) ORDER BY lang, page_id, seq",
        [v for k in missing for v in k],
    )
    rows = [(lang, page_id, seq, n, s) for lang, page_id, seq, text in cur.fetchall()
            for n, s in enumerate(sentences(text))]
    if not rows:
        return
    vectors = embed([s for *_, s in rows])
    cur.connection.begin()
    cur.executemany("INSERT IGNORE INTO sentence VALUES (%s, %s, %s, %s, %s, %s)",
                    [(*row, v) for row, v in zip(rows, vectors)])
    cur.connection.commit()


@app.get("/api/titles")
def titles(q: str):
    """Titles starting with q that exist in at least two languages, then English Wikipedia's suggestions."""
    like = re.sub(r"([\\%_])", r"\\\1", q) + "%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT a.title, a.lang FROM article a
               WHERE a.title LIKE %s AND EXISTS
                 (SELECT 1 FROM article b WHERE b.wikidata_id = a.wikidata_id AND b.lang <> a.lang)
               ORDER BY a.title LIMIT 20""",
            (like,),
        )
        out = [{"title": t, "lang": lang} for t, lang in cur.fetchall()]
    if len(out) < 20:
        try:
            found = wiki.api("en.wikipedia.org", action="opensearch", search=q, limit=10, namespace=0)[1]
        except wiki.WikiError:
            return out
        listed = {row["title"] for row in out}
        out += [{"title": t, "lang": "en"} for t in found if t not in listed][: 20 - len(out)]
    return out


# What each running /api/diff is doing, for the page's loading view: title asked for -> (stage, start).
# shortcut: in this process only, and two requests for one title share an entry; with several server
# processes, keep it in a table.
PROGRESS: dict[str, tuple[str, float]] = {}


@app.get("/api/diff")
def diff(title: str, limit: int = 10, lang: str | None = None, focus: str | None = None):
    """What a topic's editions state differently, best first; `lang` is the edition the title is from
    (any if not given: then looked up on English Wikipedia if the database does not have it), `focus`
    an edition whose findings go first."""
    start = time.monotonic()

    def progress(stage: str) -> None:
        PROGRESS[title] = (stage, start)

    progress("Looking the topic up")
    try:
        data = compare_editions(title, lang, progress)
        # findings involving the focus edition first, each group in its own order, then the limit
        data["differences"].sort(key=lambda f: focus is not None and all(m["lang"] != focus for m in f["members"]))
        data["differences"] = data["differences"][:limit]
        return data
    finally:
        PROGRESS.pop(title, None)


@app.get("/api/progress")
def progress_of(title: str):
    """The stage of a running /api/diff for this title and its seconds so far; stage null if none runs."""
    if (entry := PROGRESS.get(title)) is None:
        return {"stage": None, "seconds": 0}
    stage, start = entry
    return {"stage": stage, "seconds": round(time.monotonic() - start)}


def compare_editions(title: str, lang: str | None, progress) -> dict:
    with connect() as conn, conn.cursor() as cur:
        # The page's own edition only: on another one the same title can be another topic (de "Gift").
        cur.execute(
            "SELECT wikidata_id FROM article WHERE title = %s AND wikidata_id IS NOT NULL AND (%s IS NULL OR lang = %s) "
            "ORDER BY FIELD(lang, 'en', 'sv', 'fi') DESC, lang LIMIT 1",
            (title, lang, lang),
        )
        if row := cur.fetchone():
            wikidata_id = row[0]
            cur.execute(
                "SELECT lang, title, url FROM article WHERE wikidata_id = %s "
                "ORDER BY FIELD(lang, 'en', 'sv', 'fi') DESC, lang LIMIT 1",
                (wikidata_id,),
            )
            seed_lang, seed_title, seed_url = cur.fetchone()
            seed_host = urlparse(seed_url).netloc
        else:
            lang = lang or "en"
            try:
                p = wiki.resolve(lang, title)
            except wiki.WikiError as e:
                raise HTTPException(502, f"Wikipedia unavailable: {e}") from e
            if not p:
                raise HTTPException(404, f"no article titled {title!r} here or on {lang}.wikipedia.org")
            wikidata_id = p["wikidata_id"]
            seed_host, seed_title, seed_lang = f"{lang}.wikipedia.org", p["title"], lang
        wiki.ensure_editions(cur, wikidata_id, seed_host, seed_title, seed_lang, progress)
        cur.execute(
            "SELECT lang, page_id, title, url, text FROM article WHERE wikidata_id = %s "
            "ORDER BY FIELD(lang, 'en', 'sv', 'fi') DESC, lang",
            (wikidata_id,),
        )
        articles = cur.fetchall()
        if len(articles) < 2:
            raise HTTPException(404, f"{title!r} exists in one language only")
        progress(f"Splitting {len(articles)} editions into passages and embedding the new ones")
        ensure_chunks(cur, [(lang, page_id, text) for lang, page_id, _, _, text in articles])

        # Whole-article distance between languages, from the dataset's own vectors.
        cur.execute(
            """SELECT x.lang, y.lang, VEC_DISTANCE_COSINE(vx.embedding, vy.embedding)
               FROM article x JOIN article y ON y.wikidata_id = x.wikidata_id AND x.lang < y.lang
               JOIN article_vector vx ON vx.lang = x.lang AND vx.page_id = x.page_id
               JOIN article_vector vy ON vy.lang = y.lang AND vy.page_id = y.page_id
               WHERE x.wikidata_id = %s""",
            (wikidata_id,),
        )
        similarity = [{"a": a, "b": b, "distance": d} for a, b, d in cur.fetchall()]

        # A reload reads the differences computed for these editions by this code.
        # shortcut: passage matching also searches other topics' passages (HNSW over the corpus), so a
        # topic loaded later can change a match here without changing `state`; delete the topic's
        # diff_cache row to recompute. A precompute job would refresh affected topics instead.
        state = hashlib.sha256(json.dumps([CODE, sorted((lang, page_id) for lang, page_id, *_ in articles)]).encode()).digest()
        cur.execute("SELECT response FROM diff_cache WHERE wikidata_id = %s AND state = %s", (wikidata_id, state))
        if row := cur.fetchone():
            found, leaning = json.loads(row[0])
        else:
            def sentences_then_compare(cur, pages):  # differences() embeds sentences, then compares them
                progress(f"Embedding the sentences of {len(pages)} matched articles")
                ensure_sentences(cur, pages)
                progress("Comparing sentences: contradictions and framing")

            progress("Matching passages across languages")
            found, leaning = differences(cur, wikidata_id, sentences_then_compare)
            cur.execute("REPLACE INTO diff_cache VALUES (%s, %s, %s)", (wikidata_id, state, json.dumps([found, leaning])))

    return {
        "wikidata_id": wikidata_id,
        "articles": [{"lang": lang, "title": t, "url": u} for lang, _, t, u, _ in articles],
        "similarity": similarity,
        "differences": found,
        "leaning": leaning,
    }


@app.get("/api/context")
def context(lang: str, page_id: int, seq: int, n: int, direction: Literal["up", "down"], count: int = 3):
    """Up to `count` sentences of an article just before or after position (seq, n), in reading order:
    for expanding a quote like a diff. A whole passage seq expands up from (seq, 0) and down from (seq, 65535)."""
    up = direction == "up"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT s.seq, s.n, c.heading, s.text FROM sentence s JOIN chunk c USING (lang, page_id, seq) "
            f"WHERE s.lang = %s AND s.page_id = %s AND (s.seq, s.n) {'<' if up else '>'} (%s, %s) "
            f"ORDER BY s.seq {'DESC' if up else ''}, s.n {'DESC' if up else ''} LIMIT %s",
            (lang, page_id, seq, n, max(1, min(count, 20))),
        )
        rows = [{"seq": s, "n": i, "heading": h, "text": t} for s, i, h, t in cur.fetchall()]
    return rows[::-1] if up else rows


def strings(keys) -> dict:
    """JSON schema: an object with a string for each key."""
    return {"type": "object", "properties": {k: {"type": "string"} for k in keys}, "required": list(keys)}


class Passage(BaseModel):
    lang: str
    heading: str
    text: str


class ExplainRequest(BaseModel):
    passages: list[Passage]  # parts about the same subject, one per language
    kind: Literal["contradiction", "framing"] = "contradiction"  # a discrepancy (facts) or impartiality (tone, framing)


# What the AI checks for each kind of finding; the answer's `discrepancy` says whether it holds.
CHECKS = {
    "contradiction": (
        "for factual discrepancies: statements about the same thing that disagree (numbers, dates, names, "
        "places, outcomes). Information that only one passage has is NOT a discrepancy, and neither are "
        "differences in wording or detail. discrepancy: whether there is at least one. title: in English, "
        "at most 8 words, naming what disagrees.",
        "the disagreeing facts",
    ),
    "framing": (
        "for differences in impartiality: describing the same thing in a clearly different tone, with "
        "loaded or emotive words where another is neutral, more favourably or critically, or presenting "
        "as settled what another presents as disputed. Different facts, length or detail alone do not "
        "count. discrepancy: whether such a difference is clear. title: in English, at most 8 words, "
        "naming how the framing differs.",
        "the differently framed wording",
    ),
}


@app.post("/api/explain")
def explain(req: ExplainRequest):
    """Whether passages about the same subject, one per language, contradict each other (kind
    "contradiction") or frame it differently (kind "framing"), and how."""
    if len(req.passages) < 2:
        raise HTTPException(400, "need at least two passages")
    check, phrases = CHECKS[req.kind]
    answer = chat(
        f"You check passages about the same subject from different language editions of Wikipedia {check} "
        "summary: in English, 1-2 sentences saying what each edition states and how. Do not suggest edits "
        "or actions. highlights: for each passage's language code, the 1-4 short phrases (at most 12 words "
        f"each, copied verbatim from that passage) that state {phrases}.",
        "\n\n".join(f"[{p.lang}] section: {p.heading or '(intro)'}\n{p.text}" for p in req.passages),
        {
            "type": "object",
            "properties": {
                "discrepancy": {"type": "boolean"},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "highlights": {
                    "type": "object",
                    "properties": {p.lang: {"type": "array", "items": {"type": "string"}} for p in req.passages},
                },
            },
            "required": ["discrepancy", "title", "summary", "highlights"],
        },
    )
    texts = {p.lang: p.text for p in req.passages}
    highlights = answer.get("highlights") if isinstance(answer.get("highlights"), dict) else {}
    return {
        "discrepancy": answer.get("discrepancy") is True,
        "title": str(answer.get("title", "")),
        "summary": str(answer.get("summary", "")),
        # Only phrases that really occur: the UI marks them by exact match.
        "highlights": {
            lang: [h for h in phrases if isinstance(h, str) and h and h in texts.get(lang, "")]
            for lang, phrases in highlights.items()
            if isinstance(phrases, list)
        },
    }


class TranslateRequest(BaseModel):
    texts: dict[str, str]  # language code -> text, may contain <mark>…</mark>
    target: str


@app.post("/api/translate")
def translate(req: TranslateRequest):
    """Translate several passages in one LLM call, keeping <mark> highlights on the translated words."""
    if req.target not in TARGETS:
        raise HTTPException(400, f"target must be one of {sorted(TARGETS)}")
    # Keys are "<lang>" or "<lang>-heading"; text already in the target language is passed through.
    todo = {k: t for k, t in req.texts.items() if k.split("-")[0] != req.target and t.strip()}
    if not todo:
        return req.texts
    answer = chat(
        f"Translate each value of the user's JSON object to {TARGETS[req.target]}; each key starts with the "
        "value's source language code. Keep line breaks and Markdown list markers. Text between <mark> and </mark> is highlighted: "
        "put <mark> and </mark> around the words of your translation that correspond. "
        "Reply with an object with the same keys, values translated.",
        json.dumps(todo, ensure_ascii=False),
        strings(todo),
    )
    return {lang: str(answer.get(lang, t)) if lang in todo else t for lang, t in req.texts.items()}


@app.get("/")
def index():
    # Revalidate on every load (a 304 when unchanged): browsers otherwise reuse an old page after updates.
    return FileResponse(Path(__file__).with_name("index.html"), headers={"Cache-Control": "no-cache"})
