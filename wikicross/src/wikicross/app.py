"""API: where all the Wikipedia versions of one article frame things differently."""

import hashlib
import ipaddress
import json
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from statistics import fmean
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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
    with connect() as conn, conn.cursor() as cur:  # an empty database gets every table here
        for stmt in SCHEMA:
            cur.execute(stmt)
        widen_lang(cur)
    yield


app = FastAPI(title="WikiCross", lifespan=lifespan)

# Clients outside ALLOWED_IPS (IPs or CIDR ranges, space-separated) get at most this many requests a
# minute per zone; the home page states the same numbers. Behind Caddy the client IP comes from
# X-Forwarded-For, which Caddy sets (uvicorn --forwarded-allow-ips in the Dockerfile).
ALLOWED_IPS = [ipaddress.ip_network(n, strict=False) for n in os.environ.get("ALLOWED_IPS", "127.0.0.1 ::1").split()]
LIMITS = {"llm": 30, "api": 60}
# shortcut: in-process memory, one counter per IP and zone kept forever; fine for one server process.
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def zone(path: str) -> str | None:
    """The rate-limit zone of a path: LLM calls cost per request; progress is polled each second and
    title suggestions come with every few keystrokes, both cheap, so neither is counted."""
    if path in ("/api/explain", "/api/translate"):
        return "llm"
    return "api" if path.startswith("/api/") and path not in ("/api/progress", "/api/titles") else None


def allowed(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in ALLOWED_IPS)


@app.middleware("http")
async def rate_limit(request, call_next):
    host = request.client.host if request.client else ""
    if (z := zone(request.url.path)) and not allowed(host):
        now, hits = time.monotonic(), _hits[host, z]
        while hits and hits[0] <= now - 60:
            hits.popleft()
        if len(hits) >= LIMITS[z]:
            wait = int(hits[0] + 60 - now) + 1
            return JSONResponse({"detail": f"Too many requests: {LIMITS[z]} a minute from this address. Try again in {wait} s."},
                                429, headers={"Retry-After": str(wait)})
        hits.append(now)
    return await call_next(request)


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


def representative(editions: list[tuple[str, str, int]]) -> tuple[str, str]:
    """(lang, title) to show for a topic among its (lang, title, text length) editions: English, else
    the longest. shortcut: length stands in for popularity; page views would need another API call."""
    lang, title, _ = next((e for e in editions if e[0] == "en"), None) or max(editions, key=lambda e: e[2])
    return lang, title


def page_info(lang: str, titles: list[str]) -> dict[str, dict]:
    """Wikipedia's short description and thumbnail of these pages of one edition, by title."""
    data = wiki.api(f"{lang}.wikipedia.org", action="query", titles="|".join(titles), redirects=1,
                    prop="pageimages|description", piprop="thumbnail", pithumbsize=120)
    return {p["title"]: {"description": p.get("description"), "thumbnail": p.get("thumbnail", {}).get("source")}
            for p in data.get("query", {}).get("pages", [])}


@app.get("/api/titles")
def titles(q: str):
    """Up to 10 topics matching q, one each (not one per edition): those compared before whose title in
    any language starts with q, then English Wikipedia's suggestions. Each shows its English title, else
    the longest edition's (representative()), with Wikipedia's short description and thumbnail."""
    like = re.sub(r"([\\%_])", r"\\\1", q) + "%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT a.wikidata_id FROM article a
               WHERE a.title LIKE %s AND EXISTS
                 (SELECT 1 FROM article b WHERE b.wikidata_id = a.wikidata_id AND b.lang <> a.lang)
               ORDER BY a.title LIMIT 10""",
            (like,),
        )
        ids = [i for (i,) in cur.fetchall()]
        editions: dict[str, list] = defaultdict(list)
        if ids:
            cur.execute(f"SELECT wikidata_id, lang, title, LENGTH(text) FROM article WHERE wikidata_id IN ({', '.join(['%s'] * len(ids))})", ids)
            for qid, lang, title, length in cur.fetchall():
                editions[qid].append((lang, title, length))
    out = [{"wikidata_id": i, **dict(zip(("lang", "title"), representative(editions[i])))} for i in ids]
    try:
        found = wiki.api("en.wikipedia.org", action="query", generator="prefixsearch", gpssearch=q, gpslimit=10,
                         redirects=1, prop="pageimages|description|pageprops", piprop="thumbnail", pithumbsize=120,
                         ppprop="wikibase_item").get("query", {}).get("pages", [])
    except wiki.WikiError:
        found = []
    listed = set(ids)
    for p in sorted(found, key=lambda p: p.get("index", 0)):
        qid = p.get("pageprops", {}).get("wikibase_item")
        if len(out) < 10 and qid not in listed:
            listed.add(qid)
            out.append({"wikidata_id": qid, "lang": "en", "title": p["title"], "description": p.get("description"),
                        "thumbnail": p.get("thumbnail", {}).get("source")})
    # Description and thumbnail of the topics from the database, one call per edition.
    for lang in {s["lang"] for s in out if "description" not in s}:
        todo = [s for s in out if s["lang"] == lang and "description" not in s]
        try:
            info = page_info(lang, [s["title"] for s in todo])
        except wiki.WikiError:
            info = {}
        for s in todo:
            s.update(info.get(s["title"], {"description": None, "thumbnail": None}))
    return out


# What each running /api/diff is doing, for the page's loading view: title asked for -> (stage, start).
# shortcut: in this process only, and two requests for one title share an entry; with several server
# processes, keep it in a table.
PROGRESS: dict[str, tuple[str, float]] = {}


@app.get("/api/diff")
def diff(title: str, limit: int = 10, offset: int = 0, lang: str | None = None, focus: str | None = None,
         dialects: bool = True, langs: str | None = None):
    """What a topic's editions state differently, best first, `limit` of them from `offset` (`total`
    counts all); `lang` is the edition the title is from (any if not given: then looked up on English
    Wikipedia if the database does not have it), `focus` an edition whose findings go first.
    `dialects=false` leaves out editions without a two-letter (ISO 639-1) code: see is_dialect();
    `langs=fi,sv,ru` compares only those editions. `languages` lists every edition, filtered or not."""
    start = time.monotonic()

    def progress(stage: str) -> None:
        PROGRESS[title] = (stage, start)

    progress("Looking the topic up")
    try:
        data = compare_editions(title, lang, progress, dialects, set(langs.split(",")) if langs else None)
        # findings involving the focus edition first, each group in its own order, then the page
        data["differences"].sort(key=lambda f: focus is not None and all(m["lang"] != focus for m in f["members"]))
        data["total"] = len(data["differences"])
        data["differences"] = data["differences"][offset : offset + limit]
        return data
    finally:
        PROGRESS.pop(title, None)


def is_dialect(lang: str) -> bool:
    """An edition without a two-letter (ISO 639-1) code: a regional language or variety (bar, vro, smn,
    ast, simple, be-tarask). shortcut: a rule of thumb on the code; a curated list if it misfiles one."""
    return len(lang) != 2


@app.get("/api/progress")
def progress_of(title: str):
    """The stage of a running /api/diff for this title and its seconds so far; stage null if none runs."""
    if (entry := PROGRESS.get(title)) is None:
        return {"stage": None, "seconds": 0}
    stage, start = entry
    return {"stage": stage, "seconds": round(time.monotonic() - start)}


def narrow(found: list[dict], kept: set[str]) -> list[dict]:
    """The findings among the editions in `kept`, from those computed over every edition, without
    recomputing them. Each finding keeps the sentences of those editions, and its deviations are redone
    from the stored ones: d_i = z_i - mean(z_j, j != i) gives z_i = d_i (n-1)/n up to a shift, which
    cancels. A finding whose furthest edition is now under FRAMING_MIN_Z, or with one edition left, goes.
    shortcut: the axis stays the one chosen over every edition, and a group linked only through a
    left-out edition stays one finding; run differences() on `kept` instead if that matters."""
    out = []
    for f in found:
        n = len(f["deviations"])
        z = {lang: d * (n - 1) / n for lang, d in f["deviations"].items() if lang in kept}
        members = [m for m in f["members"] if m["lang"] in kept]
        if len(z) < 2 or len(members) < 2:
            continue
        deviations = {lang: zl - fmean(v for other, v in z.items() if other != lang) for lang, zl in z.items()}
        lang = max(deviations, key=lambda k: abs(deviations[k]))
        if abs(deviations[lang]) < compare.FRAMING_MIN_Z:
            continue
        out.append({**f, "lang": lang, "deviation": deviations[lang], "outlier": len(members) >= 3, "members": members,
                    "deviations": {k: round(d, 2) for k, d in deviations.items()}})
    out.sort(key=lambda f: -abs(f["deviation"]))
    return out


def compare_editions(title: str, lang: str | None, progress, dialects: bool = True, langs: set[str] | None = None) -> dict:
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
        every = cur.fetchall()
        articles = [a for a in every if (dialects or not is_dialect(a[0])) and (langs is None or a[0] in langs)]
        if len(articles) < 2:
            raise HTTPException(404, "fewer than two languages left: pick more" if len(every) >= 2
                                else f"{title!r} exists in one language only")
        # Always compared over every edition (computed once, then cached); filters only trim the result.
        progress(f"Splitting {len(every)} editions into passages and embedding the new ones")
        ensure_chunks(cur, [(lang, page_id, text) for lang, page_id, _, _, text in every])

        # Whole-article distance between languages, from each edition's article vector.
        cur.execute(
            """SELECT x.lang, y.lang, VEC_DISTANCE_COSINE(vx.embedding, vy.embedding)
               FROM article x JOIN article y ON y.wikidata_id = x.wikidata_id AND x.lang < y.lang
               JOIN article_vector vx ON vx.lang = x.lang AND vx.page_id = x.page_id
               JOIN article_vector vy ON vy.lang = y.lang AND vy.page_id = y.page_id
               WHERE x.wikidata_id = %s""",
            (wikidata_id,),
        )
        kept = {a[0] for a in articles}
        similarity = [{"a": a, "b": b, "distance": d} for a, b, d in cur.fetchall() if a in kept and b in kept]

        # A reload reads the differences computed for these editions by this code.
        # shortcut: passage matching also searches other topics' passages (HNSW over the corpus), so a
        # topic loaded later can change a match here without changing `state`; delete the topic's
        # diff_cache row to recompute. A precompute job would refresh affected topics instead.
        state = hashlib.sha256(json.dumps([CODE, sorted((lang, page_id) for lang, page_id, *_ in every)]).encode()).digest()
        cur.execute("SELECT response FROM diff_cache WHERE wikidata_id = %s AND state = %s", (wikidata_id, state))
        if row := cur.fetchone():
            found = json.loads(row[0])
        else:
            def sentences_then_compare(cur, pages):  # differences() embeds sentences, then compares them
                progress(f"Embedding the sentences of {len(pages)} matched articles")
                ensure_sentences(cur, pages)
                progress("Comparing sentences: framing")

            progress("Matching passages across languages")
            found = differences(cur, wikidata_id, sentences_then_compare, {a[0] for a in every})
            cur.execute("REPLACE INTO diff_cache VALUES (%s, %s, %s)", (wikidata_id, state, json.dumps(found)))
        if len(kept) < len(every):
            found = narrow(found, kept)

    return {
        "wikidata_id": wikidata_id,
        "articles": [{"lang": lang, "title": t, "url": u} for lang, _, t, u, _ in articles],
        "languages": [a[0] for a in every],
        "similarity": similarity,
        "differences": found,
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
    text: str  # the whole passage, for context
    sentence: str  # the quote shown on the card, inside `text`


class ExplainRequest(BaseModel):
    passages: list[Passage]  # parts about the same subject, one per language


KINDS = ("factual", "bias", "framing")  # the kinds of difference the AI tells apart (`kind`)


@app.post("/api/explain")
def explain(req: ExplainRequest):
    """Whether the quotes (one per language, each with its passage) disagree on the facts or present
    the same subject clearly differently, which `kind` (KINDS) of difference it is; a title and a
    description of it, and each quote in English with the words that differ marked."""
    if len(req.passages) < 2:
        raise HTTPException(400, "need at least two passages")
    answer = chat(
        "You compare quotes about the same subject from different language editions of Wikipedia, each "
        "given with the passage around it. kind: factual when they state different facts about the same "
        "thing that cannot all be true (numbers, dates, names, places, outcomes, causes, who did what); "
        "bias when one is clearly more favourable or critical, or uses loaded or emotive words where "
        "another is neutral; framing when the facts agree but are presented differently, such as settled "
        "in one and disputed in another, or with a different emphasis or perspective. If more than one "
        "applies, the strongest. One edition including facts the others leave out, length or detail alone "
        "do not count. discrepancy: whether such a difference is clear. title: in English, at most 10 "
        "words, naming which edition says what, e.g. \"Finnish calls it an invasion, Russian a border "
        "conflict\" or \"Finnish dates it 1918, Swedish 1920\". quotes: for each language code, english: "
        "the quote translated to English (unchanged if it is English), with <mark> and </mark> around the "
        "1-3 short parts that differ; heading: the section heading in English; phrases: those same parts "
        "copied verbatim from the original quote. description: in English, 2-4 sentences explaining in "
        "detail what each edition says and how they differ, quoting the marked parts of the English "
        "quotes, each quoted part wrapped in <mark> and </mark> exactly as in its quote. Every sentence "
        "must add substance: never name or justify the kind of difference (no \"this is a factual "
        "contradiction\", \"they cannot all be true\", \"not merely a difference in tone or detail\"), "
        "never restate the title. Do not suggest edits or actions.",
        "\n\n".join(f"[{p.lang}] section: {p.heading or '(intro)'}\nquote: {p.sentence}\npassage: {p.text}"
                    for p in req.passages),
        {
            "type": "object",
            "properties": {
                "discrepancy": {"type": "boolean"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "quotes": {
                    "type": "object",
                    "properties": {
                        p.lang: {
                            "type": "object",
                            "properties": {"english": {"type": "string"}, "heading": {"type": "string"},
                                           "phrases": {"type": "array", "items": {"type": "string"}}},
                            "required": ["english", "heading", "phrases"],
                        }
                        for p in req.passages
                    },
                    "required": [p.lang for p in req.passages],
                },
            },
            "required": ["discrepancy", "kind", "title", "description", "quotes"],
        },
    )
    quotes = answer.get("quotes") if isinstance(answer.get("quotes"), dict) else {}
    out = {}
    for p in req.passages:
        q = quotes.get(p.lang)
        if not isinstance(q, dict) or not isinstance(q.get("english"), str) or not q["english"].strip():
            continue  # the UI keeps this quote in its original language
        phrases = q.get("phrases") if isinstance(q.get("phrases"), list) else []
        out[p.lang] = {
            "english": q["english"],
            "heading": str(q.get("heading") or p.heading),
            # Only phrases that really occur: the UI marks them in the original by exact match.
            "phrases": [h for h in phrases if isinstance(h, str) and h and h in p.sentence],
        }
    return {
        "discrepancy": answer.get("discrepancy") is True,
        "kind": answer.get("kind") if answer.get("kind") in KINDS else None,
        "title": str(answer.get("title", "")),
        "description": str(answer.get("description", "")),
        "quotes": out,
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


WEB = Path(__file__).with_name("web")  # the web app, built from ui/ by `npm run build`


@app.get("/")
def index():
    # Revalidate on every load (a 304 when unchanged): browsers otherwise reuse an old page after updates.
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


# Its scripts and styles: file names carry a hash of their content, so a new build gets new URLs.
app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")
