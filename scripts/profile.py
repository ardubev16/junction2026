"""Profile the pipeline of a new article with VizTracer: all that /api/diff does for a topic not in the
database (fetching its editions, embedding passages, matching them, embedding sentences, comparing),
then the AI explaining the first page's findings, ten calls at once as the web app makes them.

    uv run --env-file .env scripts/profile.py Kuopio --lang fi --fresh
    uv run vizviewer profile.json

--fresh first deletes the topic's stored editions, passages, sentences and cached differences, so a
topic loaded before is profiled as new; LLM answers stay cached (their key is the prompt), so take a
topic never loaded to profile the LLM calls too. Needs the database and Modal, like the server.
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from viztracer import VizTracer

from wikicross import app, wiki
from wikicross.db import connect


def forget(title: str, lang: str) -> None:
    """Delete what the database holds of the topic, so the next diff fetches and computes it again."""
    if not (p := wiki.resolve(lang, title)):
        raise SystemExit(f"no article titled {title!r} on {lang}.wikipedia.org")
    with connect() as conn, conn.cursor() as cur:
        for table in ("sentence", "chunk"):
            cur.execute(f"DELETE t FROM {table} t JOIN article a USING (lang, page_id) WHERE a.wikidata_id = %s",
                        (p["wikidata_id"],))
        for table in ("article", "topic_editions", "diff_cache"):
            cur.execute(f"DELETE FROM {table} WHERE wikidata_id = %s", (p["wikidata_id"],))
    print(f"forgot {p['wikidata_id']}", flush=True)


def explain(finding: dict) -> bool:
    """The web app's AI call for one card: its first three quotes, the outlier's first."""
    members = sorted(finding["members"], key=lambda m: not (finding["outlier"] and m["lang"] == finding["lang"]))[:3]
    try:
        app.explain(app.ExplainRequest(passages=[
            app.Passage(lang=m["lang"], heading=m["heading"] or "", text=m["text"], sentence=m["sentence"])
            for m in members]))
        return True
    except HTTPException as e:
        print(f"AI failed: {e.detail}", flush=True)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title")
    parser.add_argument("--lang", default="en", help="the edition the title is from (default: en)")
    parser.add_argument("--fresh", action="store_true", help="delete the topic's stored data first")
    parser.add_argument("--no-ai", action="store_true", help="stop after /api/diff")
    parser.add_argument("-o", "--output", default="profile.json")
    parser.add_argument("--entries", type=int, default=5_000_000,
                        help="VizTracer's buffer, in calls: the oldest are overwritten past it")
    parser.add_argument("--min-duration", type=float, default=20,
                        help="leave out calls shorter than this, in µs (keeps the file loadable)")
    args = parser.parse_args()

    if args.fresh:
        forget(args.title, args.lang)
    with VizTracer(output_file=args.output, tracer_entries=args.entries, min_duration=args.min_duration,
                   ignore_frozen=True):
        start = time.monotonic()
        data = app.diff(args.title, lang=args.lang)
        for key, began in data["progress"]["visited"]:
            print(f"  {began:7.1f} s  {app.STEPS[key]}")
        print(f"diff: {data['total']} differences in {time.monotonic() - start:.1f} s", flush=True)
        if not args.no_ai and data["differences"]:
            ai_start = time.monotonic()
            with ThreadPoolExecutor(len(data["differences"])) as pool:
                ok = sum(pool.map(explain, data["differences"]))
            print(f"AI: {ok} of {len(data['differences'])} in {time.monotonic() - ai_start:.1f} s", flush=True)


if __name__ == "__main__":
    main()
