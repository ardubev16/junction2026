"""API: where all the Wikipedia versions of one article frame things differently."""

import hashlib
import ipaddress
import json
import re
import time
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from statistics import fmean
from typing import Annotated, Literal, cast
from urllib.parse import urlparse

import anyio.to_thread
import pymysql.connections
import pymysql.cursors
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import context as otel_context
from opentelemetry import trace
from pydantic import BaseModel, Field

from . import compare, decide, embed_gpu, translator, wiki
from .compare import MIN_EDITIONS, MIN_OUTLIER, differences, nearest_elsewhere
from .config import settings
from .db import SCHEMA, connect, widen_lang
from .embeddings import embed
from .llm import chat
from .telemetry import CACHE_LOOKUPS, STEP_SECONDS, tracer
from .wiki import Progress

MIN_CHARS = 300  # merge paragraphs until a part is at least this long: tiny parts embed noisily
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
HATNOTE = re.compile(
    r"^(pääartikkelit?|huvudartikl(ar|el)|main articles?|further information|see also)\s*:", re.IGNORECASE
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    # Endpoints are plain functions, run on worker threads that mostly wait on the LLM (~30 s a call) or
    # Wikipedia: anyio's default 40 would let a few visitors' AI calls stall every other request.
    anyio.to_thread.current_default_thread_limiter().total_tokens = 200
    with connect() as conn, conn.cursor() as cur:  # an empty database gets every table here
        for stmt in SCHEMA:
            cur.execute(stmt)
        widen_lang(cur)
    yield


app = FastAPI(title="WikiCross", lifespan=lifespan)

# RATE_LIMIT=1 turns the limit on (off by default for now). Then clients outside ALLOWED_IPS (IPs or CIDR
# ranges, space-separated) get at most this many requests a minute per zone; the home page shows the
# numbers (/api/limits). Behind Caddy the client IP comes from X-Forwarded-For, which Caddy sets
# (uvicorn --forwarded-allow-ips in the Dockerfile).
LIMITS = {"llm": 30, "api": 60}
# shortcut: in-process memory, one counter per IP and zone kept forever; fine for one server process.
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def zone(path: str) -> str | None:
    """The rate-limit zone of a path: LLM calls cost per request; progress is polled each second and
    title suggestions come with every few keystrokes, both cheap, so neither is counted. /api/diff's AI
    calls are bounded by its page (`limit`) and cached.
    """
    if path in ("/api/explain", "/api/translate", "/api/consensus"):
        return "llm"
    return "api" if path.startswith("/api/") and path not in ("/api/progress", "/api/titles") else None


def allowed(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in settings.allowed_ips)


@app.middleware("http")
async def rate_limit(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    host = request.client.host if request.client else ""
    if settings.rate_limit and (z := zone(request.url.path)) and not allowed(host):
        now, hits = time.monotonic(), _hits[host, z]
        while hits and hits[0] <= now - 60:
            hits.popleft()
        if len(hits) >= LIMITS[z]:
            wait = int(hits[0] + 60 - now) + 1
            return JSONResponse(
                {"detail": f"Too many requests: {LIMITS[z]} a minute from this address. Try again in {wait} s."},
                HTTPStatus.TOO_MANY_REQUESTS,
                headers={"Retry-After": str(wait)},
            )
        hits.append(now)
    return await call_next(request)


@app.get("/api/limits")
def limits() -> dict[str, int] | None:
    """The rate limits per address and minute (as LIMITS), or null when off: the home page states them."""
    return LIMITS if settings.rate_limit else None


def split(text: str) -> list[tuple[str, str]]:
    """Markdown -> [(heading, part)]: paragraphs (lines) merged up to MIN_CHARS, never across a heading."""
    parts: list[tuple[str, str]] = []
    heading, buf, skip_level = "", [], 0

    def flush() -> None:
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


def ensure_chunks(cur: pymysql.cursors.Cursor, articles: list[tuple[str, int, str]]) -> None:
    """Split and embed the articles (lang, page_id, text) that have no parts yet: one embed() call."""
    if not articles:
        return
    keys = [(lang, page_id) for lang, page_id, _ in articles]
    cur.execute(
        f"SELECT DISTINCT lang, page_id FROM chunk WHERE (lang, page_id) IN ({_in(keys)})", [v for k in keys for v in k]
    )
    done = set(cur.fetchall())
    rows = [
        (lang, page_id, i, h, t)
        for lang, page_id, text in articles
        if (lang, page_id) not in done
        for i, (h, t) in enumerate(split(text))
    ]
    if not rows:
        return
    vectors = embed([f"{h}\n\n{t}" if h else t for *_, h, t in rows])
    conn = cast("pymysql.connections.Connection", cur.connection)  # None only once the cursor is closed
    conn.begin()  # an interrupted run leaves all of an article's parts or none
    cur.executemany(
        "INSERT IGNORE INTO chunk VALUES (%s, %s, %s, %s, %s, %s)",
        [(*row, v) for row, v in zip(rows, vectors, strict=True)],
    )
    conn.commit()


# A sentence ends at . ! ? followed by an uppercase letter of any alphabet, a quote or a bracket. Not
# before a digit or a lowercase letter: "(k. 1985)", "3. syyskuuta", "z. B. der" stay whole; a sentence
# starting with a year joins the one before, which is harmless.
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=\S)")
OPENERS = '"“”«„('
MIN_SENTENCE = 30  # shorter pieces ("Ks. myös.") join a neighbour in the same line


def sentences(part: str) -> list[str]:
    """A part's sentences; table rows and list items count as one sentence each."""
    out: list[str] = []
    for raw in part.splitlines():
        line = raw.strip()
        if not line or (line.startswith("|") and set(line) <= set("|-: ")):
            continue  # blank, or a table separator row
        if line.startswith(("|", "- ")):
            out.append(line)
            continue
        mine, buf = [], ""
        pieces, start = [], 0
        for m in SENTENCE_BREAK.finditer(line):
            if line[m.end()] in OPENERS or line[m.end()].isupper():
                pieces.append(line[start : m.start()].strip())
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


def ensure_sentences(cur: pymysql.cursors.Cursor, pages: list[tuple[str, int]]) -> None:
    """Embed the sentences of the pages' parts (parts must exist) that have none yet: one embed() call."""
    if not pages:
        return
    cur.execute(
        f"SELECT DISTINCT lang, page_id FROM sentence WHERE (lang, page_id) IN ({_in(pages)})",
        [v for k in pages for v in k],
    )
    missing = sorted(set(map(tuple, pages)) - set(cur.fetchall()))
    if not missing:
        return
    cur.execute(
        f"SELECT lang, page_id, seq, text FROM chunk WHERE (lang, page_id) IN ({_in(missing)}) "
        "ORDER BY lang, page_id, seq",
        [v for k in missing for v in k],
    )
    rows = [
        (lang, page_id, seq, n, s) for lang, page_id, seq, text in cur.fetchall() for n, s in enumerate(sentences(text))
    ]
    if not rows:
        return
    vectors = embed([s for *_, s in rows])
    conn = cast("pymysql.connections.Connection", cur.connection)  # None only once the cursor is closed
    conn.begin()
    cur.executemany(
        "INSERT IGNORE INTO sentence VALUES (%s, %s, %s, %s, %s, %s)",
        [(*row, v) for row, v in zip(rows, vectors, strict=True)],
    )
    conn.commit()


def representative(editions: list[tuple[str, str, int]]) -> tuple[str, str]:
    """(lang, title) to show for a topic among its (lang, title, text length) editions: English, else
    the longest. shortcut: length stands in for popularity; page views would need another API call.
    """
    lang, title, _ = next((e for e in editions if e[0] == "en"), None) or max(editions, key=lambda e: e[2])
    return lang, title


def page_info(lang: str, titles: list[str]) -> dict[str, dict]:
    """Wikipedia's short description and thumbnail of these pages of one edition, by title."""
    data = wiki.api(
        f"{lang}.wikipedia.org",
        action="query",
        titles="|".join(titles),
        redirects=1,
        prop="pageimages|description",
        piprop="thumbnail",
        pithumbsize=120,
    )
    return {
        p["title"]: {"description": p.get("description"), "thumbnail": p.get("thumbnail", {}).get("source")}
        for p in data.get("query", {}).get("pages", [])
    }


MAX_SUGGESTIONS = 10  # topics /api/titles lists


@app.get("/api/titles")
def titles(q: str) -> list[dict]:
    """Up to 10 topics matching q, one each (not one per edition): those compared before whose title in
    any language starts with q, then English Wikipedia's suggestions. Each shows its English title, else
    the longest edition's (representative()), with Wikipedia's short description and thumbnail.
    """
    like = re.sub(r"([\\%_])", r"\\\1", q) + "%"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT DISTINCT a.wikidata_id FROM article a
               WHERE a.title LIKE %s AND EXISTS
                 (SELECT 1 FROM article b WHERE b.wikidata_id = a.wikidata_id AND b.lang <> a.lang)
               ORDER BY a.title LIMIT {MAX_SUGGESTIONS}""",
            (like,),
        )
        ids = [i for (i,) in cur.fetchall()]
        editions: dict[str, list] = defaultdict(list)
        if ids:
            cur.execute(
                "SELECT wikidata_id, lang, title, LENGTH(text) FROM article "
                f"WHERE wikidata_id IN ({', '.join(['%s'] * len(ids))})",
                ids,
            )
            for qid, lang, title, length in cur.fetchall():
                editions[qid].append((lang, title, length))
    out = [{"wikidata_id": i, **dict(zip(("lang", "title"), representative(editions[i]), strict=True))} for i in ids]
    try:
        found = (
            wiki.api(
                "en.wikipedia.org",
                action="query",
                generator="prefixsearch",
                gpssearch=q,
                gpslimit=MAX_SUGGESTIONS,
                redirects=1,
                prop="pageimages|description|pageprops",
                piprop="thumbnail",
                pithumbsize=120,
                ppprop="wikibase_item",
            )
            .get("query", {})
            .get("pages", [])
        )
    except wiki.WikiError:
        found = []
    listed = set(ids)
    for p in sorted(found, key=lambda p: p.get("index", 0)):
        qid = p.get("pageprops", {}).get("wikibase_item")
        if len(out) < MAX_SUGGESTIONS and qid not in listed:
            listed.add(qid)
            out.append(
                {
                    "wikidata_id": qid,
                    "lang": "en",
                    "title": p["title"],
                    "description": p.get("description"),
                    "thumbnail": p.get("thumbnail", {}).get("source"),
                }
            )
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


# The steps of a /api/diff, in order, as the loading view lists them; progress(key, detail) moves to one.
# Steps a request does not need (a topic fetched before skips "editions"; cached differences skip the
# three after "passages") are passed over.
STEPS = {
    "lookup": "Looking the topic up",
    "editions": "Fetching its editions from Wikipedia",
    "passages": "Splitting the editions into passages and embedding them",
    "match": "Matching passages across languages",
    "sentences": "Embedding the sentences of matched passages",
    "compare": "Comparing the sentences",
    "decide": "Checking which are real disagreements",
}
# What each running /api/diff is doing: title asked for -> {"visited": [step key, seconds from the start
# when it began] so far, "detail", "start"}. Two requests for one title share the first one's entry (the
# second finds its work done, or waits for it). shortcut: in this process only; with several server
# processes, keep it in a table.
PROGRESS: dict[str, dict] = {}


def report(entry: dict | None) -> dict:
    """A diff's progress as the loading view reads it: the `steps` (key and label, in order), those
    `visited` ([key, start second], the last one current), its `detail` and the `seconds` so far.
    """
    steps = [{"key": k, "label": v} for k, v in STEPS.items()]
    if entry is None:
        return {"steps": steps, "visited": [], "detail": "", "seconds": 0}
    return {
        "steps": steps,
        "visited": entry["visited"],
        "detail": entry["detail"],
        "seconds": round(time.monotonic() - entry["start"], 1),
    }


@app.get("/api/diff")
def diff(
    title: str,
    *,
    limit: Annotated[int, Query(ge=0, le=30)] = 10,
    offset: int = 0,
    lang: str | None = None,
    focus: str | None = None,
    dialects: bool = True,
    langs: str | None = None,
    kinds: str | None = None,
) -> dict:
    """What a topic's editions state differently, `limit` findings from `offset` (`total` counts all);
    `lang` is the edition the title is from (any if not given: then looked up on English Wikipedia if the
    database does not have it), `focus` an edition whose findings go first. `dialects=false` leaves out
    editions without a two-letter (ISO 639-1) code: see is_dialect(); `langs=fi,sv,ru` compares only those
    editions; `kinds=factual,bias` keeps only findings of those KINDS. `languages` lists every edition,
    filtered or not. The decision model judges every finding (judge()): those it finds no disagreement in
    are left out, `kinds` counts the rest by kind, and the strongest come first. Each finding's members
    come in the order cards show them; cards ask /api/explain for the AI's explanation as they are
    scrolled to. `progress`: the steps this request took, each with its start second, and its `seconds`.
    """
    mine: dict = {"visited": [], "detail": "", "start": time.monotonic()}
    owner = PROGRESS.setdefault(title, mine) is mine  # only the first request for a title is polled
    # The current step as a trace span, made current so the step's HTTP calls and SQL nest under it.
    step: dict = {"span": None, "token": None}

    def end_step() -> None:
        if step["span"]:
            key, began = mine["visited"][-1]
            STEP_SECONDS.record(time.monotonic() - mine["start"] - began, {"step": key})
            otel_context.detach(step["token"])
            step["span"].end()
            step["span"] = None

    def progress(key: str, detail: str = "") -> None:
        if not mine["visited"] or mine["visited"][-1][0] != key:
            end_step()
            mine["visited"].append([key, round(time.monotonic() - mine["start"], 1)])
            step["span"] = tracer.start_span(f"step {key}", attributes={"wikicross.title": title})
            step["token"] = otel_context.attach(trace.set_span_in_context(step["span"]))
        mine["detail"] = detail

    progress("lookup")
    try:
        data = compare_editions(
            title, lang, progress, dialects=dialects, langs=set(langs.split(",")) if langs else None
        )
        found = data.pop("differences")
        card_order(found, focus)
        found, data["unchecked"] = judge(found, progress)
        data["kinds"] = {k: sum(f["kind"] == k for f in found) for k in KINDS}
        wanted = set(kinds.split(",")) if kinds else None
        found = [f for f in found if wanted is None or f["kind"] in wanted]
        # findings involving the focus edition first, then the strongest
        found.sort(key=lambda f: (focus is not None and all(m["lang"] != focus for m in f["members"]), -rank(f)))
        data["total"] = len(found)
        data["differences"] = found[offset : offset + limit]
        data["progress"] = report(mine)
        return data
    finally:
        end_step()
        if owner:
            PROGRESS.pop(title, None)


def card_order(found: list[dict], focus: str | None = None) -> None:
    """Each finding's members in the order its card shows them, the first SHOWN being the ones the models
    judge: the focus edition's quote first, then the outlier's, then the rest in order.
    """
    for f in found:
        f["members"].sort(key=lambda m, f=f: (m["lang"] != focus, not (f["outlier"] and m["lang"] == f["lang"])))


ISO_639_1_LEN = 2  # letters in an ISO 639-1 language code


def is_dialect(lang: str) -> bool:
    """An edition without a two-letter (ISO 639-1) code: a regional language or variety (bar, vro, smn,
    ast, simple, be-tarask). shortcut: a rule of thumb on the code; a curated list if it misfiles one.
    """
    return len(lang) != ISO_639_1_LEN


@app.get("/api/progress")
def progress_of(title: str) -> dict:
    """The steps of a /api/diff running for this title, and its progress: see report()."""
    return report(PROGRESS.get(title))


def narrow(found: list[dict], kept: set[str]) -> list[dict]:
    """The findings among the editions in `kept`, from those computed over every edition, without
    recomputing them. Each finding keeps the sentences of those editions, and its deviations are redone
    from the stored ones: d_i = z_i - mean(z_j, j != i) gives z_i = d_i (n-1)/n up to a shift, which
    cancels. A finding whose furthest edition is now under FRAMING_MIN_Z, or with one edition left, goes.
    shortcut: the axis stays the one chosen over every edition, and a group linked only through a
    left-out edition stays one finding; run differences() on `kept` instead if that matters.
    """
    out: list[dict] = []
    for f in found:
        n = len(f["deviations"])
        z = {lang: d * (n - 1) / n for lang, d in f["deviations"].items() if lang in kept}
        members = [m for m in f["members"] if m["lang"] in kept]
        if len(z) < MIN_EDITIONS or len(members) < MIN_EDITIONS:
            continue
        deviations = {lang: zl - fmean(v for other, v in z.items() if other != lang) for lang, zl in z.items()}
        lang = max(deviations, key=lambda k: abs(deviations[k]))
        if abs(deviations[lang]) < compare.FRAMING_MIN_Z:
            continue
        out.append(
            {
                **f,
                "lang": lang,
                "deviation": deviations[lang],
                "outlier": len(members) >= MIN_OUTLIER,
                "members": members,
                "deviations": {k: round(d, 2) for k, d in deviations.items()},
            }
        )
    out.sort(key=lambda f: -abs(f["deviation"]))
    return out


def compare_editions(
    title: str,
    lang: str | None,
    progress: Progress,
    *,
    dialects: bool = True,
    langs: set[str] | None = None,
) -> dict:
    with connect() as conn, conn.cursor() as cur:
        # The page's own edition only: on another one the same title can be another topic (de "Gift").
        cur.execute(
            "SELECT wikidata_id FROM article WHERE title = %s AND wikidata_id IS NOT NULL "
            "AND (%s IS NULL OR lang = %s) "
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
        # One request at a time indexes a topic: others for it (by any title or edition) wait here, then find
        # it stored and its differences cached. A MariaDB lock, freed when this connection closes, errors
        # included; after an hour of waiting the request goes ahead anyway.
        cur.execute("SELECT GET_LOCK(%s, 0)", (f"wikicross:{wikidata_id}",))
        if not cur.fetchone()[0]:
            progress("lookup", "waiting for another request that is loading this topic")
            cur.execute("SELECT GET_LOCK(%s, 3600)", (f"wikicross:{wikidata_id}",))
        wiki.ensure_editions(cur, wikidata_id, seed_host, seed_title, seed_lang, progress=progress)
        cur.execute(
            "SELECT lang, page_id, title, url, text FROM article WHERE wikidata_id = %s "
            "ORDER BY FIELD(lang, 'en', 'sv', 'fi') DESC, lang",
            (wikidata_id,),
        )
        every = cur.fetchall()
        articles = [a for a in every if (dialects or not is_dialect(a[0])) and (langs is None or a[0] in langs)]
        if len(articles) < MIN_EDITIONS:
            raise HTTPException(
                404,
                "fewer than two languages left: pick more"
                if len(every) >= MIN_EDITIONS
                else f"{title!r} exists in one language only",
            )
        # Always compared over every edition (computed once, then cached); filters only trim the result.
        progress("passages", f"{len(every)} editions; only new ones are embedded")
        ensure_chunks(cur, [(lang, page_id, text) for lang, page_id, _, _, text in every])

        kept = {a[0] for a in articles}

        # A reload reads the differences computed for these editions by this code.
        # shortcut: passage matching also searches other topics' passages (HNSW over the corpus), so a
        # topic loaded later can change a match here without changing `state`; delete the topic's
        # diff_cache row to recompute. A precompute job would refresh affected topics instead.
        state = hashlib.sha256(
            json.dumps([CODE, sorted((lang, page_id) for lang, page_id, *_ in every)]).encode()
        ).digest()
        cur.execute("SELECT response FROM diff_cache WHERE wikidata_id = %s AND state = %s", (wikidata_id, state))
        if row := cur.fetchone():
            CACHE_LOOKUPS.add(1, {"cache": "diff", "result": "hit"})
            found = json.loads(row[0])
        else:
            CACHE_LOOKUPS.add(1, {"cache": "diff", "result": "miss"})

            # differences() embeds sentences, then compares them
            def sentences_then_compare(cur: pymysql.cursors.Cursor, pages: list[tuple[str, int]]) -> None:
                progress("sentences", f"{len(pages)} articles")
                ensure_sentences(cur, pages)
                progress("compare")

            progress("match")
            found = differences(cur, wikidata_id, sentences_then_compare, {a[0] for a in every})
            cur.execute("REPLACE INTO diff_cache VALUES (%s, %s, %s)", (wikidata_id, state, json.dumps(found)))
        if len(kept) < len(every):
            found = narrow(found, kept)

    return {
        "wikidata_id": wikidata_id,
        "articles": [{"lang": lang, "title": t, "url": u} for lang, _, t, u, _ in articles],
        "languages": [a[0] for a in every],
        "differences": found,
    }


def judge(found: list[dict], progress: Progress) -> tuple[list[dict], str | None]:
    """The findings the decision model sees a disagreement in (decide.decide() of the first SHOWN quotes),
    each with its `kind` and `decision`; and why some went unchecked, if they did: those stay, kind None.
    """
    decisions, error = decide.decide(
        [[{"lang": m["lang"], "sentence": m["sentence"]} for m in f["members"][:SHOWN]] for f in found],
        lambda done, total: progress("decide", f"{done} of {total}"),
    )
    kept = []
    for f, d in zip(found, decisions, strict=True):
        if d is None or d["kind"] != decide.NONE:
            kept.append({**f, "kind": d and d["kind"], "decision": d})
    return kept, error


def rank(f: dict) -> float:
    """How strongly a finding is a disagreement, by the decision model: P(disagreement) times strength
    (0-2) + 1; unchecked findings after the checked, in their order (the axis deviation).
    """
    d = f["decision"]
    return d["real"] * (1 + d["strength"]) if d else -1


@app.get("/api/context")
def context(
    lang: str, page_id: int, seq: int, n: int, direction: Literal["up", "down"], *, count: int = 3
) -> list[dict]:
    """Up to `count` sentences of an article just before or after position (seq, n), in reading order:
    for expanding a quote like a diff. A whole passage seq expands up from (seq, 0) and down from (seq, 65535).
    """
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


KINDS = decide.KINDS  # the kinds of difference: `kind`, from the decision model
SHOWN = 3  # quotes a card shows, those the AI explains and the decision model judges (ui/shared/util.ts)

DIGIT_GROUP = r"[.,'\s\u00a0\u202f]"  # what may group a number's digits: 122,590 = 122.590 = 122 590


def locate(phrase: str, sentence: str) -> str | None:
    """The part of the sentence a phrase the LLM copied stands for: exact, else ignoring case, spacing and
    how numbers group their digits. None if it is not there (e.g. given in English, not the quote's language).
    """
    phrase = phrase.strip()
    if not phrase or phrase in sentence:
        return phrase or None
    pattern = ""
    for i, ch in enumerate(phrase):
        between_digits = 0 < i < len(phrase) - 1 and phrase[i - 1].isdigit() and phrase[i + 1].isdigit()
        if between_digits and re.fullmatch(DIGIT_GROUP, ch):
            pattern += DIGIT_GROUP + "?"
        elif ch.isspace():
            pattern += "" if pattern.endswith(r"\s+") else r"\s+"
        else:
            pattern += re.escape(ch)
        if ch.isdigit() and i + 1 < len(phrase) and phrase[i + 1].isdigit():
            pattern += DIGIT_GROUP + "?"  # 122590 in the phrase, 122 590 in the sentence
    m = re.search(pattern, sentence, re.IGNORECASE)
    return m.group(0) if m else None


def explain(passages: list[dict]) -> dict:
    """Whether the quotes (finding members: lang, heading, its passage `text` and the quote `sentence`,
    one per language) make a claim about one same `subject` and differ about it, which `kind` (KINDS) of
    difference it is; a title and a description of it, and each quote in English with the words that
    differ marked. Measured on labelled findings by `python -m wikicross.evals explain`.
    """
    answer = chat(
        "You compare quotes from different language editions of Wikipedia about one topic. Each quote comes "
        "with its section heading and, for context only, the passage around it.\n"
        "subject: the one specific thing every quote itself states a value or judgement of, so that the "
        'quotes can be compared directly, in English (e.g. "Kuopio\'s population", "when the war ended", '
        '"how the attack is judged"). Only the quotes count: a claim found only in a passage does not. '
        "Empty if the quotes do not all state something about the same specific thing, even when they are "
        "about the same product, place or event: e.g. one gives the number of data centers and another the "
        "number of employees; one names a feature and another a different feature; one calls a service the "
        "most popular and another a key to the company's success.\n"
        "discrepancy: true only if subject is not empty and the quotes clearly differ about it. kind: factual "
        "when they state facts about it that cannot all be true (numbers, dates, names, places, outcomes, "
        "causes, who did what); bias when one is clearly more favourable or critical, or uses loaded or "
        "emotive words where another is neutral; framing when the facts agree but are presented differently, "
        "such as settled in one and disputed in another. If more than one applies, the strongest. A quote "
        "giving details the others leave out, or differing only in length or detail, is not a discrepancy.\n"
        "title: in English, at most 10 words, naming which edition says what about the subject, e.g. "
        '"Finnish calls it an invasion, Russian a border conflict" or "Finnish dates it 1918, Swedish 1920".\n'
        "quotes: for each language code, in this order: phrases: the 1-3 short parts of the quote that differ, "
        'copied character for character from the line starting "quote:" in its own language (not from '
        "the passage, not translated); english: the quote, and only the quote (never the passage), "
        "translated to English, unchanged if it is English, with <mark> and </mark> around the translation "
        "of each of those parts; heading: the section heading in English.\n"
        "description: in English, 2-4 sentences on what each edition says about the subject and how they "
        "differ, quoting the marked parts of the English quotes, each wrapped in <mark> and </mark> exactly "
        "as in its English quote (never the original-language words). Every sentence must add substance: "
        'never name or justify the kind of difference (no "this is a factual contradiction", "they cannot '
        'all be true"), never restate the title. Do not suggest edits or actions.',
        # The quote last, after its passage: models translated the passage when the quote came first.
        "\n\n".join(
            f"[{p['lang']}] section: {p['heading'] or '(intro)'}\n"
            f"passage (context only): {p['text']}\n"
            f"quote: {p['sentence']}"
            for p in passages
        ),
        {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "discrepancy": {"type": "boolean"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "title": {"type": "string"},
                "quotes": {
                    "type": "object",
                    "properties": {
                        p["lang"]: {
                            "type": "object",
                            "properties": {
                                # Before english: asked after it, models copied their English marks.
                                "phrases": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "the 1-3 parts that differ, copied from this quote, "
                                    "in its own language",
                                },
                                "english": {
                                    "type": "string",
                                    "description": "this quote alone in English, those parts marked",
                                },
                                "heading": {"type": "string"},
                            },
                            "required": ["phrases", "english", "heading"],
                        }
                        for p in passages
                    },
                    "required": [p["lang"] for p in passages],
                },
                "description": {"type": "string"},
            },
            "required": ["subject", "discrepancy", "kind", "title", "quotes", "description"],
        },
    )
    quotes = q if isinstance(q := answer.get("quotes"), dict) else {}
    out = {}
    for p in passages:
        q = quotes.get(p["lang"])
        if not isinstance(q, dict) or not isinstance(q.get("english"), str) or not q["english"].strip():
            continue  # the UI keeps this quote in its original language
        phrases = q.get("phrases") if isinstance(q.get("phrases"), list) else []
        out[p["lang"]] = {
            "english": q["english"],
            "heading": str(q.get("heading") or p["heading"]),
            # As they occur in the quote: the UI marks them in the original by exact match.
            "phrases": [s for h in phrases if isinstance(h, str) and (s := locate(h, p["sentence"]))],
        }
    subject = str(answer.get("subject") or "").strip()
    # The differing words must be in the quotes themselves, two of them at least: models compared figures
    # found only in a passage, or quotes about different things.
    visible = sum(bool(q["phrases"]) for q in out.values()) >= MIN_EDITIONS
    return {
        "subject": subject,
        "discrepancy": answer.get("discrepancy") is True and bool(subject) and visible,
        "kind": answer.get("kind") if answer.get("kind") in KINDS else None,
        "title": str(answer.get("title", "")),
        "description": str(answer.get("description", "")),
        "quotes": out,
    }


ENGLISH = {"en", "simple"}  # editions already in English (Simple English Wikipedia)


def translate(texts: dict[str, str]) -> dict[str, str]:
    """Translate several texts to English (translator.py: Azure, or the LLM for languages it lacks),
    keeping <mark> highlights on the translated words. Keys are "<lang>" or "<lang>-heading"; English
    text is passed through.
    """
    todo = {k: t for k, t in texts.items() if k.removesuffix("-heading") not in ENGLISH and t.strip()}
    if not todo:
        return texts
    english = translator.to_english([(k.removesuffix("-heading"), t) for k, t in todo.items()])
    answer = dict(zip(todo, english, strict=True))
    return {k: answer.get(k, t) for k, t in texts.items()}


class Quote(BaseModel):
    """A finding member's sentence, by its place: the text comes from the database, never the client."""

    lang: str = Field(max_length=20)
    page_id: int
    seq: int
    n: int


def passages_of(quotes: list[Quote]) -> list[dict]:
    """The quotes as finding members (lang, heading, passage `text`, quote `sentence`), read from the
    database in the order given; unknown ones are left out.
    """
    keys = [(q.lang, q.page_id, q.seq, q.n) for q in quotes]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT s.lang, s.page_id, s.seq, s.n, c.heading, c.text, s.text "
            "FROM sentence s JOIN chunk c USING (lang, page_id, seq) "
            f"WHERE (s.lang, s.page_id, s.seq, s.n) IN ({_in(keys)})",
            [v for k in keys for v in k],
        )
        found = {tuple(r[:4]): {"lang": r[0], "heading": r[4], "text": r[5], "sentence": r[6]} for r in cur.fetchall()}
    return [found[k] for k in keys if k in found]


class ExplainRequest(BaseModel):
    quotes: list[Quote] = Field(min_length=MIN_EDITIONS, max_length=SHOWN)  # a card's first SHOWN, in its order


@app.post("/api/explain")
def explain_quotes(req: ExplainRequest) -> dict:
    """explain() of a finding's first SHOWN quotes, by place: a card asks once it nears the view, so only
    findings someone reads are explained and translated.
    """
    passages = passages_of(req.quotes)
    if len(passages) < MIN_EDITIONS:
        raise HTTPException(HTTPStatus.NOT_FOUND, "these quotes are not in the database")
    return explain(passages)


def consensus(subject: str, passages: list[dict], others: list[dict]) -> list[dict]:
    """What the editions say about the subject a finding's quotes (lang, sentence) disagree on, the quotes'
    and the other editions' nearest sentences (`others`, compare.nearest_elsewhere): their positions, most
    editions first, each a `claim` in English and its `editions`. Editions not stating it are left out.
    """
    known = [p["lang"] for p in passages] + [o["lang"] for o in others]
    if not others:
        return []  # nothing to compare against: the quotes alone are the finding
    answer = chat(
        "Quotes from different language editions of Wikipedia disagree about a subject; sentences from other "
        "editions may state it too. positions: the editions grouped by what they state about the subject, "
        "one position per distinct value or claim. claim: that value or claim in English, at most 8 words, "
        "with the date it is given for if stated. editions: the language codes stating it, the same value "
        "however worded; a rounded value goes with the value it rounds. Every quote's edition is in a "
        "position; an edition whose sentence does not state the subject itself is in none.",
        f"subject: {subject}\n\n"
        + "\n".join(f"quote [{p['lang']}]: {p['sentence']}" for p in passages)
        + "\n\n"
        + "\n".join(f"edition [{o['lang']}]: {o['sentence']}" for o in others),
        {
            "type": "object",
            "properties": {
                "positions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "string"},
                            "editions": {"type": "array", "items": {"type": "string", "enum": known}},
                        },
                        "required": ["claim", "editions"],
                    },
                },
            },
            "required": ["positions"],
        },
    )
    seen: set[str] = set()  # an edition in one position only: the first the LLM put it in
    positions = []
    for p in answer.get("positions") or []:
        if not isinstance(p, dict) or not isinstance(p.get("editions"), list):
            continue
        langs = [lang for lang in p["editions"] if lang in known and lang not in seen]
        seen.update(langs)
        if langs:
            positions.append({"claim": str(p.get("claim") or ""), "editions": langs})
    return sorted(positions, key=lambda p: -len(p["editions"]))


class ConsensusRequest(BaseModel):
    quotes: list[Quote] = Field(min_length=MIN_EDITIONS, max_length=SHOWN)  # those the AI explained
    subject: str = Field(min_length=1, max_length=300)  # the explanation's


@app.post("/api/consensus")
def consensus_of(req: ConsensusRequest) -> dict:
    """consensus() of a finding the AI found a factual disagreement in, asked for by its card, with how
    many other editions were asked (`asked`) and the sentences of those stating the subject (`sentences`).
    """
    passages = passages_of(req.quotes)
    if len(passages) < MIN_EDITIONS:
        raise HTTPException(HTTPStatus.NOT_FOUND, "these quotes are not in the database")
    with connect() as conn, conn.cursor() as cur:
        others = nearest_elsewhere(cur, [(q.lang, q.page_id, q.seq, q.n) for q in req.quotes])
    positions = consensus(req.subject, passages, others)
    stated = {lang for p in positions for lang in p["editions"]}
    return {
        "positions": positions,
        "asked": len(others),
        "sentences": {o["lang"]: o["sentence"] for o in others if o["lang"] in stated},
    }


class TranslateRequest(BaseModel):
    quotes: list[Quote] = Field(min_length=1, max_length=200)  # one finding's, one per edition
    paragraphs: bool = False  # their passages with the quote marked, instead of the quotes and headings


@app.post("/api/translate")
def translate_quotes(req: TranslateRequest) -> dict[str, str]:
    """Quotes in English, by language ("<lang>", "<lang>-heading"), or with `paragraphs` their passages,
    the quote marked: what a card shows beyond the AI's explanation. Unknown quotes are left out.
    """
    texts = {}
    for p in passages_of(req.quotes):
        if req.paragraphs:
            texts[p["lang"]] = p["text"].replace(p["sentence"], f"<mark>{p['sentence']}</mark>")
        else:
            texts[p["lang"]] = p["sentence"]
            if p["heading"]:
                texts[f"{p['lang']}-heading"] = p["heading"]
    return translate(texts) if texts else {}


WEB = Path(__file__).with_name("web")  # the web app, built from ui/ by `make web` (or the Dockerfile)


@app.get("/")
def index() -> Response:  # a Response, not a union: FastAPI would take a union for a response model
    if not (WEB / "index.html").exists():
        return JSONResponse(
            {"detail": "The web app is not built: run `make web`."}, status_code=HTTPStatus.SERVICE_UNAVAILABLE
        )
    # Revalidate on every load (a 304 when unchanged): browsers otherwise reuse an old page after updates.
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


# Its scripts and styles: file names carry a hash of their content, so a new build gets new URLs.
app.mount("/assets", StaticFiles(directory=WEB / "assets", check_dir=False), name="assets")
