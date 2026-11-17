"""Profile the pipeline of a new article with VizTracer: all that /api/diff does for a topic not in the
database (fetching its editions, embedding passages, matching them, embedding sentences, comparing, then
the AI explaining the first page's ten findings at once).

    uv run --env-file .env scripts/profile.py Kuopio --lang fi --fresh   # into profiles/Kuopio.json
    uv run vizviewer profiles/Kuopio.json

--fresh profiles a topic loaded before as new: it first deletes the topic's stored editions, passages,
sentences and cached differences, and makes the LLM calls instead of reading their cached answers
(which it then updates). Needs the database and Modal, like the server.
"""

import argparse
import time
from pathlib import Path

from viztracer import VizTracer

from wikicross import app, llm, wiki
from wikicross.db import connect


def forget(title: str, lang: str) -> None:
    """Delete what the database holds of the topic, so the next diff fetches and computes it again."""
    if not (p := wiki.resolve(lang, title)):
        raise SystemExit(f"no article titled {title!r} on {lang}.wikipedia.org")
    with connect() as conn, conn.cursor() as cur:
        for table in ("sentence", "chunk"):
            cur.execute(
                f"DELETE t FROM {table} t JOIN article a USING (lang, page_id) WHERE a.wikidata_id = %s",
                (p["wikidata_id"],),
            )
        for table in ("article", "topic_editions", "diff_cache"):
            cur.execute(f"DELETE FROM {table} WHERE wikidata_id = %s", (p["wikidata_id"],))
    print(f"forgot {p['wikidata_id']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title")
    parser.add_argument("--lang", default="en", help="the edition the title is from (default: en)")
    parser.add_argument("--fresh", action="store_true", help="profile it as new: forget its data and LLM answers")
    parser.add_argument("--no-ai", action="store_true", help="stop before the AI step (an empty first page)")
    parser.add_argument("-o", "--output", type=Path, help="the trace file (default: profiles/TITLE.json)")
    parser.add_argument(
        "--entries",
        type=int,
        default=5_000_000,
        help="VizTracer's buffer, in calls: the oldest are overwritten past it",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=20,
        help="leave out calls shorter than this, in µs (keeps the file loadable)",
    )
    args = parser.parse_args()

    output = args.output or Path("profiles", f"{args.title.replace('/', '_')}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        forget(args.title, args.lang)
        llm.READ_CACHE = False
    with VizTracer(
        output_file=str(output), tracer_entries=args.entries, min_duration=args.min_duration, ignore_frozen=True
    ):
        start = time.monotonic()
        data = app.diff(args.title, lang=args.lang, limit=0 if args.no_ai else 10)
        for key, began in data["progress"]["visited"]:
            print(f"  {began:7.1f} s  {app.STEPS[key]}")
        failed = [f["ai"]["error"] for f in data["differences"] if "error" in f["ai"]]
        for error in failed:
            print(f"AI failed: {error}")
        print(
            f"diff: {data['total']} differences, AI {len(data['differences']) - len(failed)} of "
            f"{len(data['differences'])}, in {time.monotonic() - start:.1f} s",
            flush=True,
        )


if __name__ == "__main__":
    main()
