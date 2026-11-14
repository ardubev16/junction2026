"""API: where the fi, sv and en Wikipedia articles on one topic frame things differently or state very different figures."""

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .compare import differences
from .db import SCHEMA, connect
from .embeddings import embed
from .llm import chat

MIN_CHARS = 300  # merge paragraphs until a part is at least this long: tiny parts embed noisily
TARGETS = {"en": "English"}  # languages the UI can translate into
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
    yield


app = FastAPI(title="langdiff", lifespan=lifespan)


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


def ensure_chunks(cur, lang: str, page_id: int, text: str) -> None:
    cur.execute("SELECT 1 FROM chunk WHERE lang = %s AND page_id = %s LIMIT 1", (lang, page_id))
    if cur.fetchone():
        return
    parts = split(text)
    vectors = embed([f"{h}\n\n{t}" if h else t for h, t in parts])
    cur.executemany(
        "INSERT IGNORE INTO chunk VALUES (%s, %s, %s, %s, %s, %s)",
        [(lang, page_id, i, h, t, v) for i, ((h, t), v) in enumerate(zip(parts, vectors))],
    )


# A sentence ends at . ! ? followed by a capital, quote or bracket. Not before a digit: "(k. 1985)",
# "3. syyskuuta" stay whole; a sentence starting with a year joins the one before, which is harmless.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ\"“”(])")
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
        for piece in SENTENCE_END.split(line):
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


def ensure_sentences(cur, lang: str, page_id: int) -> None:
    """Embed the sentences of an article's parts (which must be embedded already)."""
    cur.execute("SELECT 1 FROM sentence WHERE lang = %s AND page_id = %s LIMIT 1", (lang, page_id))
    if cur.fetchone():
        return
    cur.execute("SELECT seq, text FROM chunk WHERE lang = %s AND page_id = %s ORDER BY seq", (lang, page_id))
    rows = [(seq, n, s) for seq, text in cur.fetchall() for n, s in enumerate(sentences(text))]
    vectors = embed([s for _, _, s in rows])
    cur.executemany(
        "INSERT IGNORE INTO sentence VALUES (%s, %s, %s, %s, %s, %s)",
        [(lang, page_id, seq, n, s, v) for (seq, n, s), v in zip(rows, vectors)],
    )


@app.get("/api/titles")
def titles(q: str):
    """Titles starting with q that exist in at least two languages."""
    like = re.sub(r"([\\%_])", r"\\\1", q) + "%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT a.title, a.lang FROM article a
               WHERE a.title LIKE %s AND EXISTS
                 (SELECT 1 FROM article b WHERE b.wikidata_id = a.wikidata_id AND b.lang <> a.lang)
               ORDER BY a.title LIMIT 20""",
            (like,),
        )
        return [{"title": t, "lang": lang} for t, lang in cur.fetchall()]


@app.get("/api/diff")
def diff(title: str, limit: int = 10):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT wikidata_id FROM article WHERE title = %s AND wikidata_id IS NOT NULL "
            "ORDER BY FIELD(lang, 'fi', 'sv', 'en') LIMIT 1",
            (title,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, f"no article titled {title!r}")
        wikidata_id = row[0]
        cur.execute(
            "SELECT lang, page_id, title, url, text FROM article WHERE wikidata_id = %s "
            "ORDER BY FIELD(lang, 'fi', 'sv', 'en')",
            (wikidata_id,),
        )
        articles = cur.fetchall()
        if len(articles) < 2:
            raise HTTPException(404, f"{title!r} exists in one language only")
        for lang, page_id, _, _, text in articles:
            ensure_chunks(cur, lang, page_id, text)

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

        found = differences(cur, wikidata_id, ensure_sentences)

    return {
        "wikidata_id": wikidata_id,
        "articles": [{"lang": lang, "title": t, "url": u} for lang, _, t, u, _ in articles],
        "similarity": similarity,
        "differences": found[:limit],
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


@app.post("/api/explain")
def explain(req: ExplainRequest):
    """Whether passages about the same subject, one per language, contradict each other, and how."""
    if len(req.passages) < 2:
        raise HTTPException(400, "need at least two passages")
    answer = chat(
        "You check passages about the same subject from different language editions of Wikipedia "
        "for factual discrepancies: statements about the same thing that disagree (numbers, dates, names, "
        "places, outcomes). Information that only one passage has is NOT a discrepancy, and neither are "
        "differences in wording or detail. discrepancy: whether there is at least one. title: in English, "
        "at most 8 words, naming what disagrees. summary: in English, 1-2 sentences saying what each "
        "edition states. Do not suggest edits or actions. highlights: for each passage's language code, "
        "the 1-4 short phrases (at most 12 words each, copied verbatim from that passage) that state "
        "the disagreeing facts.",
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
    return FileResponse(Path(__file__).with_name("index.html"))
