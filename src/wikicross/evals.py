"""Evaluations on labelled findings (evals/findings.json): how well the AI explains them, and how well
bge-m3's distances tell a shared claim from two different ones. Not unit tests: they call the LLM or
Modal, and their scores move with the model. CI runs them on demand and weekly
(.github/workflows/evals.yaml); each exits 1 below its floor.

    uv run --env-file .env python -m wikicross.evals explain     # the LLM: needs the database (its cache)
    uv run --env-file .env python -m wikicross.evals embeddings  # bge-m3 on Modal
    uv run --env-file .env python -m wikicross.evals add Google en 9 different   # label a finding

A case is one finding's first SHOWN quotes, each with its passage, and a label:
- "differ": the quotes make one claim and differ about it: the AI should confirm a discrepancy;
- "agree": one claim, stated alike: no discrepancy;
- "different": claims about different things: no discrepancy, and ideally not grouped at all.
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import HTTPException

from . import app, llm
from .compare import FRAMING_MAX
from .db import SCHEMA, connect, widen_lang
from .embeddings import embed

CASES = Path(__file__).parents[2] / "evals" / "findings.json"
LABELS = ("differ", "agree", "different")
Label = Literal["differ", "agree", "different"]
MARK = re.compile(r"<mark>(.*?)</mark>", re.DOTALL)
OVERLONG = 2.2  # an English quote this many times its original's length is a translated passage
# Floors, set below what the current prompt and model measure: a run under one is a regression.
FLOORS = {"accuracy": 0.8, "highlighted": 0.85, "not_overlong": 0.9, "embeddings_accuracy": 0.6}


def load() -> list[dict]:
    return json.loads(CASES.read_text())


def score_explanation(case: dict, x: dict) -> dict:
    """One explain() answer against its case: the verdict, and for a confirmed difference, whether each
    quote has a highlight found in the original and an English quote that is the quote, not its passage.
    """
    expected = case["label"] == "differ"
    quotes = []
    for p in case["passages"]:
        q = x["quotes"].get(p["lang"])
        plain = MARK.sub(r"\1", q["english"]) if q else ""
        quotes.append(
            {
                "lang": p["lang"],
                "highlighted": bool(q and q["phrases"] and MARK.search(q["english"])),
                "overlong": len(plain) > OVERLONG * len(p["sentence"]),
            }
        )
    return {
        "id": case["id"],
        "label": case["label"],
        "correct": x["discrepancy"] == expected,
        "discrepancy": x["discrepancy"],
        "subject": x.get("subject", ""),
        "title": x["title"],
        "quotes": quotes,
    }


def explain_eval() -> int:
    llm.READ_CACHE = False  # the model as it answers now
    with connect() as conn, conn.cursor() as cur:  # an empty database (CI) gets its tables
        for stmt in SCHEMA:
            cur.execute(stmt)
        widen_lang(cur)
    cases = load()

    def run(case: dict) -> dict:
        try:
            return score_explanation(case, app.explain(case["passages"]))
        except HTTPException as e:
            return {"id": case["id"], "label": case["label"], "error": str(e.detail)}

    with ThreadPoolExecutor(4) as pool:  # providers cap requests a minute
        scores = list(pool.map(run, cases))
    for s in scores:
        verdict = "ERROR " + s["error"] if "error" in s else ("ok " if s["correct"] else "WRONG ") + s["title"]
        print(f"{s['id']:<14} {s['label']:<9} {verdict}")
    answered = [s for s in scores if "error" not in s]
    confirmed = [q for s in answered if s["discrepancy"] and s["label"] == "differ" for q in s["quotes"]]
    quotes = [q for s in answered for q in s["quotes"]]
    result = {
        "accuracy": sum(s["correct"] for s in answered) / len(scores),  # an error counts as wrong
        "highlighted": sum(q["highlighted"] for q in confirmed) / max(1, len(confirmed)),
        "not_overlong": 1 - sum(q["overlong"] for q in quotes) / max(1, len(quotes)),
    }
    return report(result)


def distance(a: bytes, b: bytes) -> float:
    """Cosine distance of two bge-m3 vectors, as MariaDB's VEC_DISTANCE_COSINE."""
    u, v = np.frombuffer(a, "<f4"), np.frombuffer(b, "<f4")
    return float(1 - u @ v / (np.linalg.norm(u) * np.linalg.norm(v)))


def embeddings_eval() -> int:
    """Every pair of quotes in a case: grouped as one claim (distance <= FRAMING_MAX) as they should be
    ("differ", "agree") or not ("different")? Also the distances per label, to place the threshold.
    """
    cases = load()
    pairs = [(c, a, b) for c in cases for i, a in enumerate(c["passages"]) for b in c["passages"][i + 1 :]]
    vectors = embed([s for _, a, b in pairs for s in (a["sentence"], b["sentence"])])
    by_label: dict[str, list[float]] = {label: [] for label in LABELS}
    correct = 0
    for k, (case, a, b) in enumerate(pairs):
        d = distance(vectors[2 * k], vectors[2 * k + 1])
        by_label[case["label"]].append(d)
        ok = (d <= FRAMING_MAX) == (case["label"] != "different")
        correct += ok
        print(f"{case['id']:<14} {case['label']:<9} {a['lang']}-{b['lang']:<8} {d:.3f} {'ok' if ok else 'WRONG'}")
    for label, ds in by_label.items():
        if ds:
            print(
                f"{label:<9} distance min {min(ds):.3f}  mean {np.mean(ds):.3f}  max {max(ds):.3f}  ({len(ds)} pairs)"
            )
    print(f"FRAMING_MAX = {FRAMING_MAX}")
    return report({"embeddings_accuracy": correct / len(pairs)})


def report(result: dict[str, float]) -> int:
    failed = [k for k, v in result.items() if v < FLOORS[k]]
    for k, v in result.items():
        print(f"{k}: {v:.2f} (floor {FLOORS[k]}){'  BELOW' if k in failed else ''}")
    return 1 if failed else 0


def add(title: str, lang: str, index: int, label: Label) -> None:
    """Label the finding at `index` (0 = best) of a topic and append it to the cases: its first SHOWN
    quotes, as the AI gets them. Needs the database and Modal, like the server.
    """
    finding = app.diff(title, lang=lang, offset=index, limit=1, ai=False)["differences"][0]
    case_id = f"{title}#{index}"
    passages = [{k: m[k] for k in ("lang", "heading", "text", "sentence")} for m in finding["members"][: app.SHOWN]]
    cases = [c for c in load() if c["id"] != case_id] if CASES.exists() else []
    cases.append({"id": case_id, "label": label, "passages": passages})
    CASES.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(f"{case_id}: {label}, " + ", ".join(f"[{p['lang']}] {p['sentence'][:60]}" for p in passages))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("explain", help="the LLM's verdicts, highlights and translations")
    commands.add_parser("embeddings", help="bge-m3 distances against FRAMING_MAX")
    adding = commands.add_parser("add", help="label a finding of a topic as a new case")
    adding.add_argument("title")
    adding.add_argument("lang")
    adding.add_argument("index", type=int)
    adding.add_argument("label", choices=LABELS)
    args = parser.parse_args()
    if args.command == "add":
        add(args.title, args.lang, args.index, args.label)
    else:
        sys.exit(explain_eval() if args.command == "explain" else embeddings_eval())


if __name__ == "__main__":
    main()
