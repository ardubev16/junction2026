"""Live Wikipedia: every Latin- and Cyrillic-script edition of a topic, the first time it is asked for.

Fetched once per topic through the MediaWiki API (plain-text extracts), converted to Markdown with
appendix sections (bibliography, links) removed and stored in `article`. Editions are fetched FETCHERS
at a time; Wikimedia answers bursts with HTTP 429 and
Retry-After, which api() waits out.
"""

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from urllib.parse import urlparse

import httpx
import numpy as np

from .embeddings import embed, embed_cached

UA = "WikiCross/0.1 (Junction 2026 hackathon; 43483037+ardubev16@users.noreply.github.com)"
SCRIPTS = ("LATIN", "CYRILLIC")  # Unicode script names of the editions compared
SCRIPT_SHARE = 0.9  # letters that must be in SCRIPTS for an edition to be compared
RETRIES = 3
# Editions fetched at once: each is on its own host (fi.wikipedia.org, …), and api() waits out 429s.
FETCHERS = 8
# An appendix line (a citation, a link) is shorter than this; a section with a longer line holds prose.
# Measured on Stepan Bandera's 47 editions: appendix lines at most 306 chars, closing content 450+.
PROSE = 400

# Section names that are lists of sources and links, not content (app.SKIP's words, plus generic ones
# small editions use); any language's heading is classified by its nearest anchor among these and CONTENT.
APPENDIX = [
    "lähteet", "viitteet", "kirjallisuutta", "aiheesta muualla", "katso myös", "huomautukset",
    "källor", "fotnoter", "noter", "referenser", "litteratur", "externa länkar", "se även", "vidare läsning",
    "references", "notes", "sources", "bibliography", "citations", "further reading", "external links", "see also",
    "links", "literature", "footnotes", "other projects", "related articles",
    "примечания", "литература", "ссылки", "см. также", "источники", "примітки", "джерела", "посилання",
    "бележки", "извори", "литература и извори",
]
CONTENT = [
    "Early life", "Biography", "Career", "Political activity", "Death", "Legacy", "History", "Background",
    "Assessment", "Commemoration", "Varhaiset vuodet", "Elämäkerta", "Ura", "Kuolema", "Perintö", "Historia",
    "Tausta", "Tidiga år", "Biografi", "Karriär", "Död", "Eftermäle", "Historia", "Bakgrund",
    "Биография", "Ранние годы", "Смерть", "История", "Біографія", "Життєпис",
]
HEADING = re.compile(r"^(=+)\s*(.+?)\s*\1$")


class WikiError(Exception):
    pass


def in_scripts(text: str) -> bool:
    """At least SCRIPT_SHARE of the text's letters (and at least one) are in SCRIPTS: a Cyrillic article
    may quote Latin names, but Greek, Arabic or CJK editions are left out."""
    letters = [c for c in text if c.isalpha()]
    known = sum(unicodedata.name(c, "").startswith(SCRIPTS) for c in letters)
    return bool(letters) and known >= SCRIPT_SHARE * len(letters)


def api(host: str, **params) -> dict:
    """One MediaWiki API call; waits out 429 and 5xx answers (Retry-After) up to RETRIES times."""
    params |= {"format": "json", "formatversion": 2}
    for attempt in range(RETRIES + 1):
        try:
            r = httpx.get(f"https://{host}/w/api.php", params=params, headers={"User-Agent": UA},
                          timeout=30, follow_redirects=True)
        except httpx.HTTPError as e:
            raise WikiError(f"{host}: {e!r}") from e
        if r.status_code == 200:
            return r.json()
        if (r.status_code == 429 or r.status_code >= 500) and attempt < RETRIES:
            retry_after = r.headers.get("retry-after", "")
            time.sleep(min(int(retry_after) if retry_after.isdigit() else 5, 30))
            continue
        raise WikiError(f"{host}: HTTP {r.status_code}")
    raise AssertionError("unreachable")


def page(host: str, title: str, text: bool) -> dict | None:
    """A page with its Wikidata id and language links (and plain text if asked), or None if missing."""
    data = api(
        host, action="query", titles=title, redirects=1,
        prop="pageprops|info|langlinks" + ("|extracts" if text else ""),
        ppprop="wikibase_item", inprop="url", lllimit="max", llprop="url", explaintext=1, exsectionformat="wiki",
    )
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or pages[0].get("invalid"):
        return None
    p = pages[0]
    return {
        "page_id": p["pageid"],
        "title": p["title"],
        "url": p["fullurl"],
        "wikidata_id": p.get("pageprops", {}).get("wikibase_item"),
        "langlinks": [(link["lang"], link["url"], link["title"]) for link in p.get("langlinks", [])],
        "extract": p.get("extract") or "",
    }


def headings(extract: str) -> list[tuple[int, str]]:
    """(level, text) of each `== H ==` heading line."""
    return [(len(m.group(1)), m.group(2)) for line in extract.splitlines() if (m := HEADING.match(line.strip()))]


def markdown(title: str, extract: str, appendix: set[str]) -> str:
    """The extract as Markdown (`#` headings), without the sections whose heading is in `appendix`."""
    out, skip_level = [f"# {title}"], 0
    for line in extract.splitlines():
        line = line.strip()
        if m := HEADING.match(line):
            level, heading = len(m.group(1)), m.group(2)
            if skip_level and level <= skip_level:
                skip_level = 0
            if not skip_level and heading in appendix:
                skip_level = level
            if not skip_level:
                out.append("#" * level + " " + heading)
        elif line and not skip_level:
            out.append(line)
    return "\n".join(out)


def _unit(vectors: list[bytes]) -> np.ndarray:
    v = np.stack([np.frombuffer(b, "<f4") for b in vectors])
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


@lru_cache
def _anchors() -> tuple[np.ndarray, int]:
    """Unit vectors of APPENDIX + CONTENT, and how many of them are appendix names."""
    return _unit(embed_cached(APPENDIX + CONTENT)), len(APPENDIX)


def appendix_headings(texts: list[str]) -> set[str]:
    """Headings whose nearest anchor is an appendix name: one embed() call for all of them."""
    if not texts:
        return set()
    anchors, n = _anchors()
    nearest = (_unit(embed(texts)) @ anchors.T).argmax(1)
    return {t for t, i in zip(texts, nearest) if i < n}


def trailing_appendix(extract: str, appendix: set[str]) -> set[str]:
    """Headings of the article's closing appendix: walking back from the end, the top-level sections
    classified as appendix and without prose (empty sections pass), with everything under and after
    them. Wikipedia keeps references and links last; the classifier alone mistakes some content
    headings ("Views", "Peringatan", "Eftirmæli") for appendix names."""
    lines = [line.strip() for line in extract.splitlines()]
    heads = [(i, len(m.group(1)), m.group(2)) for i, line in enumerate(lines) if (m := HEADING.match(line))]
    if not heads:
        return set()
    top = min(level for _, level, _ in heads)
    sections = [(i, h) for i, level, h in heads if level == top] + [(len(lines), "")]
    cut = None
    for (start, heading), (end, _) in reversed(list(zip(sections, sections[1:]))):
        text = [line for line in lines[start + 1 : end] if line and not HEADING.match(line)]
        if heading in appendix and max(map(len, text), default=0) < PROSE:
            cut = start
        elif text:
            break
    return set() if cut is None else {h for i, _, h in heads if i >= cut}


def resolve(lang: str, title: str) -> dict | None:
    """The page titled `title` on lang.wikipedia.org, if it exists and has a Wikidata id."""
    p = page(f"{lang}.wikipedia.org", title, text=False)
    return p if p and p["wikidata_id"] else None


def ensure_editions(cur, wikidata_id: str, seed_host: str, seed_title: str, seed_lang: str,
                    progress=lambda message: None) -> None:
    """Fetch and store every edition of the topic in SCRIPTS not in the DB yet, once per topic
    and set of scripts (a topic fetched before Cyrillic was added fetches its Cyrillic editions once).
    `progress(message)` is told what is happening, for the page's loading view."""
    cur.execute("SELECT 1 FROM topic_editions WHERE wikidata_id = %s AND scripts = %s", (wikidata_id, ",".join(SCRIPTS)))
    if cur.fetchone():
        return
    progress("Looking up the other language editions on Wikipedia")
    try:
        seed = page(seed_host, seed_title, text=False)
        reason = "seed page missing" if not seed else (
            f"seed is {seed['wikidata_id']}" if seed["wikidata_id"] != wikidata_id else None)
    except WikiError as e:
        reason = str(e)
    if reason:
        print(f"editions of {wikidata_id}: {reason}", flush=True)
        return

    cur.execute("SELECT lang FROM article WHERE wikidata_id = %s", (wikidata_id,))
    have = {lang for (lang,) in cur.fetchall()}
    candidates = [(lang, url, title) for lang, url, title in seed["langlinks"] + [(seed_lang, seed["url"], seed["title"])]
                  if lang not in have]
    skipped = sum(not in_scripts(title) for _, _, title in candidates)
    wanted = [c for c in candidates if in_scripts(c[2])]
    fetched, failed = [], False
    with ThreadPoolExecutor(FETCHERS) as pool:
        jobs = {pool.submit(page, urlparse(url).netloc, title, True): lang for lang, url, title in wanted}
        for done, job in enumerate(as_completed(jobs), 1):
            progress(f"Fetched {done} of {len(wanted)} editions from Wikipedia")
            try:
                p = job.result()
            except WikiError as e:
                print(f"editions of {wikidata_id}: {e}", flush=True)
                failed = True
                continue
            if not p or p["wikidata_id"] != wikidata_id or not in_scripts(p["extract"][:3000]):
                skipped += 1
                continue
            fetched.append({**p, "lang": jobs[job]})
    fetched.sort(key=lambda e: e["lang"])  # completion order varies; keep runs comparable

    progress(f"Storing {len(fetched)} new editions")
    classified = appendix_headings(sorted({h for e in fetched for _, h in headings(e["extract"])}))
    dropped = [trailing_appendix(e["extract"], classified) for e in fetched]
    cur.connection.begin()
    for e, drop in zip(fetched, dropped):
        cur.execute("INSERT IGNORE INTO article VALUES (%s, %s, %s, %s, %s, %s)",
                    (e["lang"], e["page_id"], wikidata_id, e["title"], e["url"], markdown(e["title"], e["extract"], drop)))
    if not failed:
        cur.execute("INSERT INTO topic_editions (wikidata_id, scripts) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE scripts = VALUES(scripts), fetched_at = CURRENT_TIMESTAMP",
                    (wikidata_id, ",".join(SCRIPTS)))
    cur.connection.commit()
    print(f"editions of {wikidata_id}: {len(fetched)} fetched, {skipped} skipped, "
          f"{'some failed' if failed else 'complete'}", flush=True)
    print(f"appendix headings: {sorted(set().union(*dropped))}", flush=True)
