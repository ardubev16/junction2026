"""API: given an article title, the parts of the article that differ the most between fi, sv and en."""

import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .db import SCHEMA, connect
from .discrepancy import conflicts
from .llm import chat

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = "bge-m3"  # the model the dataset's vectors were made with
MIN_CHARS = 300  # merge paragraphs until a part is at least this long: tiny parts embed noisily
TARGETS = {"en": "English"}  # languages the UI can translate into
SAME_SUBJECT = 0.35  # cosine distance under which two mutually nearest parts are about one subject
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


def embed(texts: list[str]) -> list[bytes]:
    out = []
    for i in range(0, len(texts), 32):
        r = httpx.post(
            f"{OLLAMA}/api/embed",
            json={"model": MODEL, "input": texts[i : i + 32], "truncate": True},
            timeout=600,
        )
        r.raise_for_status()
        out += [np.asarray(v, "<f4").tobytes() for v in r.json()["embeddings"]]
    return out


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

        # Pairs of parts about the same subject: in two languages, each is the other's nearest
        # part, and they are close. Only such pairs can state one fact differently.
        cur.execute(
            """WITH c AS (SELECT c.* FROM chunk c JOIN article a USING (lang, page_id)
                          WHERE a.wikidata_id = %s),
               d AS (SELECT x.lang AS a, x.seq AS aseq, y.lang AS b, y.seq AS bseq,
                            VEC_DISTANCE_COSINE(x.embedding, y.embedding) AS dist
                     FROM c x JOIN c y ON x.lang < y.lang),
               r AS (SELECT d.*,
                            ROW_NUMBER() OVER (PARTITION BY a, aseq, b ORDER BY dist) AS ra,
                            ROW_NUMBER() OVER (PARTITION BY b, bseq, a ORDER BY dist) AS rb
                     FROM d)
               SELECT r.a, ca.heading, ca.text, r.b, cb.heading, cb.text, r.dist
               FROM r JOIN c ca ON ca.lang = r.a AND ca.seq = r.aseq
                      JOIN c cb ON cb.lang = r.b AND cb.seq = r.bseq
               WHERE r.ra = 1 AND r.rb = 1 AND r.dist <= %s""",
            (wikidata_id, SAME_SUBJECT),
        )
        pairs = []
        for a, aheading, atext, b, bheading, btext, dist in cur.fetchall():
            if found := conflicts(atext, btext, dist):
                pairs.append({
                    "distance": dist,
                    "conflicts": found,
                    "passages": [
                        {"lang": a, "heading": aheading, "text": atext},
                        {"lang": b, "heading": bheading, "text": btext},
                    ],
                })
        pairs.sort(key=lambda p: (-len(p["conflicts"]), p["distance"]))

    return {
        "wikidata_id": wikidata_id,
        "articles": [{"lang": lang, "title": t, "url": u} for lang, _, t, u, _ in articles],
        "similarity": similarity,
        "pairs": pairs[:limit],
    }


def strings(keys) -> dict:
    """JSON schema: an object with a string for each key."""
    return {"type": "object", "properties": {k: {"type": "string"} for k in keys}, "required": list(keys)}


class Passage(BaseModel):
    lang: str
    heading: str
    text: str


class ExplainRequest(BaseModel):
    passages: list[Passage]  # two parts about the same subject, in two languages


@app.post("/api/explain")
def explain(req: ExplainRequest):
    """Whether two passages about the same subject contradict each other, and how."""
    if len(req.passages) != 2:
        raise HTTPException(400, "need exactly two passages")
    answer = chat(
        "You check two passages about the same subject from different language editions of Wikipedia "
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
