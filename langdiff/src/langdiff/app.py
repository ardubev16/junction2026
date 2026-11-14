"""API: given an article title, the parts of the article that differ the most between fi, sv and en."""

import hashlib
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

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = "bge-m3"  # the model the dataset's vectors were made with
MIN_CHARS = 300  # merge paragraphs until a part is at least this long: tiny parts embed noisily
# OpenAI-compatible chat endpoint for translations; the key comes from the environment (.env).
LLM_URL = os.environ.get("LLM_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3.5-super-vl:free")
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

        # For every part, its nearest part in each other language. A part far from everything in
        # some language is content that language does not have (or tells differently).
        cur.execute(
            """WITH c AS (SELECT c.* FROM chunk c JOIN article a USING (lang, page_id)
                          WHERE a.wikidata_id = %s),
               d AS (SELECT x.lang, x.seq, y.lang AS olang, y.seq AS oseq,
                            VEC_DISTANCE_COSINE(x.embedding, y.embedding) AS dist
                     FROM c x JOIN c y ON y.lang <> x.lang),
               r AS (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY lang, seq, olang ORDER BY dist) AS rn
                     FROM d)
               SELECT r.lang, r.seq, cx.heading, cx.text, r.olang, cy.heading, cy.text, r.dist
               FROM r JOIN c cx ON cx.lang = r.lang AND cx.seq = r.seq
                      JOIN c cy ON cy.lang = r.olang AND cy.seq = r.oseq
               WHERE r.rn = 1""",
            (wikidata_id,),
        )
        parts: dict[tuple[str, int], dict] = {}
        for lang, seq, heading, text, olang, oheading, otext, dist in cur.fetchall():
            p = parts.setdefault((lang, seq), {"lang": lang, "heading": heading, "text": text, "nearest": []})
            p["nearest"].append({"lang": olang, "heading": oheading, "text": otext, "distance": dist})
        for p in parts.values():
            p["score"] = max(n["distance"] for n in p["nearest"])
        ranked = sorted(parts.values(), key=lambda p: p["score"], reverse=True)[:limit]

    return {
        "wikidata_id": wikidata_id,
        "articles": [{"lang": lang, "title": t, "url": u} for lang, _, t, u, _ in articles],
        "similarity": similarity,
        "parts": ranked,
    }


def chat(system: str, user: str) -> dict:
    """One JSON-answering LLM call, cached in MariaDB (the free tier allows 20 requests a minute)."""
    key = hashlib.sha256(json.dumps([LLM_MODEL, system, user]).encode()).digest()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT response FROM llm_cache WHERE k = %s", (key,))
        if row := cur.fetchone():
            return json.loads(row[0])
        if "OPENROUTER_API_KEY" not in os.environ:
            raise HTTPException(503, "OPENROUTER_API_KEY not set: start with  uv run --env-file .env langdiff")
        try:
            r = httpx.post(
                f"{LLM_URL}/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                json={
                    "model": LLM_MODEL,
                    "max_tokens": 8192,
                    "temperature": 0,
                    "reasoning": {"enabled": False},  # OpenRouter: same quality here, ~0.8 s instead of ~7 s
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                },
                timeout=300,
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"LLM request failed: {e}") from e
        if r.is_error:  # e.g. OpenRouter's free-model daily limit: pass its message on
            try:
                message = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = r.text[:300]
            raise HTTPException(502, f"LLM error {r.status_code}: {message}")
        content = r.json()["choices"][0]["message"]["content"] or ""
        try:  # the model may wrap the JSON in a code fence
            answer = json.loads(content[content.find("{") : content.rfind("}") + 1])
        except ValueError as e:
            raise HTTPException(502, f"LLM did not answer with JSON: {content[:200]!r}") from e
        cur.execute("REPLACE INTO llm_cache VALUES (%s, %s)", (key, json.dumps(answer)))
        return answer


class Passage(BaseModel):
    lang: str
    heading: str
    text: str


class ExplainRequest(BaseModel):
    passages: list[Passage]  # the divergent part first, then its closest part in each other language


@app.post("/api/explain")
def explain(req: ExplainRequest):
    """What differs between a part and its closest counterparts: a headline, a summary, and the
    verbatim phrases carrying the difference in each language."""
    first, *others = req.passages
    if not others:
        raise HTTPException(400, "need at least two passages")
    answer = chat(
        "You compare passages about the same topic from different language editions of Wikipedia. "
        f"The first passage, from {first.lang}.wikipedia, has no close counterpart in the other editions; "
        "each other passage is the closest one its edition has. Describe in English what differs: "
        "facts, details or emphasis one edition has and the others lack, or where they disagree. "
        "Do not suggest edits or actions. Reply with JSON only:\n"
        '{"title": "<headline, at most 8 words>", "summary": "<1-2 sentences>", '
        '"highlights": {"<language code>": ["<short phrase copied verbatim from that passage>", ...]}}\n'
        "Highlights: the 1-4 phrases per passage (at most 12 words each) that carry the core difference.",
        "\n\n".join(f"[{p.lang}] section: {p.heading or '(intro)'}\n{p.text}" for p in req.passages),
    )
    texts = {p.lang: p.text for p in req.passages}
    highlights = answer.get("highlights") if isinstance(answer.get("highlights"), dict) else {}
    return {
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
        "Reply with a JSON object with the same keys, values translated, nothing else.",
        json.dumps(todo, ensure_ascii=False),
    )
    return {lang: str(answer.get(lang, t)) if lang in todo else t for lang, t in req.texts.items()}


@app.get("/")
def index():
    return FileResponse(Path(__file__).with_name("index.html"))
