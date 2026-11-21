"""Evaluations on labelled findings (evals/findings.json): how well the decision model tells real
disagreements apart, how well the AI explains them, and how well bge-m3's distances tell a shared claim
from two different ones. Not unit tests: they call the models or Modal, and their scores move with the
model. CI runs them on demand and weekly (.github/workflows/evals.yaml); each exits 1 below its floor.

    uv run --env-file .env python -m wikicross.evals decide      # the decision model: needs the database
    uv run --env-file .env python -m wikicross.evals explain     # the LLM: needs the database (its cache)
    uv run --env-file .env python -m wikicross.evals embeddings  # bge-m3 on Modal
    uv run --env-file .env python -m wikicross.evals yield       # detection on TOPICS: Wikipedia, Modal, decider
    uv run --env-file .env python -m wikicross.evals add Google en 9 different   # label a finding

A case is one finding's first SHOWN quotes, each with its passage, and a label:
- "differ": the quotes make one claim and differ about it: a real disagreement, to keep;
- "agree": one claim, stated alike: to drop;
- "different": claims about different things: to drop, and ideally not grouped at all.
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

from . import app, decide, llm
from .compare import FRAMING_MAX
from .db import SCHEMA, connect, widen_lang
from .embeddings import embed

CASES = Path(__file__).parents[2] / "evals" / "findings.json"
LABELS = ("differ", "agree", "different")
Label = Literal["differ", "agree", "different"]
MARK = re.compile(r"<mark>(.*?)</mark>", re.DOTALL)
OVERLONG = 2.2  # an English quote this many times its original's length is a translated passage
# Floors, set below what the current prompt and model measure: a run under one is a regression.
FLOORS = {
    "decide_accuracy": 0.9,
    "outlier_accuracy": 0.9,
    "accuracy": 0.8,
    "highlighted": 0.85,
    "not_overlong": 0.9,
    "embeddings_accuracy": 0.6,
}
# The reference topics of the yield eval: a city (94 editions), a war (a long article in many editions)
# and a company (127 editions); a topic keeping more than YIELD_DROP fewer findings than in YIELD fails.
TOPICS = ("Kuopio", "Talvisota", "Google")
YIELD = CASES.with_name("yield.json")
YIELD_DROP = 0.15


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


def schema() -> None:
    with connect() as conn, conn.cursor() as cur:  # an empty database (CI) gets its tables
        for stmt in SCHEMA:
            cur.execute(stmt)
        widen_lang(cur)


def decide_eval() -> int:
    """The decision model's verdict on each case: a disagreement (kept) only for "differ"; and for a case
    naming its `outlier` edition, whether the model names the same.
    """
    llm.READ_CACHE = False  # the model as it answers now
    schema()
    cases = load()
    decisions, error = decide.decide(
        [[{"lang": p["lang"], "sentence": p["sentence"]} for p in c["passages"]] for c in cases], lambda *_: None
    )
    correct, outliers = 0, []
    for case, d in zip(cases, decisions, strict=True):
        ok = d is not None and decide.kept(d) == (case["label"] == "differ")
        correct += ok
        if "outlier" in case:
            outliers.append(d is not None and d["outlier"] == case["outlier"])
        verdict = (
            f"{d['kind']:<8} P(disagreement) {d['real']:.2f}  strength {d['strength']:.2f}  outlier {d['outlier']}"
            if d
            else "ERROR"
        )
        print(f"{case['id']:<14} {case['label']:<9} {'ok   ' if ok else 'WRONG'} {verdict}")
    if error:
        print(error)
    result = {"decide_accuracy": correct / len(cases)}  # an error counts as wrong
    if outliers:
        result["outlier_accuracy"] = sum(outliers) / len(outliers)
    return report(result)


def explain_eval() -> int:
    llm.READ_CACHE = False  # the model as it answers now
    schema()
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


def yield_eval(*, update: bool) -> int:
    """Detection's yield on the reference topics: per topic, its candidates and how many the decision
    model keeps, by kind, against evals/yield.json. A topic keeping more than YIELD_DROP fewer than its
    baseline fails: the regression check for compare.py's thresholds and grouping. `update` saves this run
    as the baseline. Counts depend on the database (passages are matched over its whole corpus), so the
    baseline is per database and not committed: save it on main's code, then run the change (CI does the
    same). A topic not in the database is fetched and embedded first.
    """
    schema()
    now = {}
    for title in TOPICS:
        found = app.compare_editions(title, None, lambda *_: None)["differences"]
        app.card_order(found)
        kept, error = app.judge(found, lambda *_: None)
        if error:
            print(f"{title}: {error}")
            return 1
        now[title] = {"candidates": len(found), "kept": len(kept)} | {
            k: sum(f["kind"] == k for f in kept) for k in app.KINDS
        }
    base = json.loads(YIELD.read_text()) if YIELD.exists() else {}
    failed = [t for t in TOPICS if t in base and now[t]["kept"] < (1 - YIELD_DROP) * base[t]["kept"]]
    for t, n in now.items():
        b = base.get(t, {})
        print(
            f"{t:<10} candidates {n['candidates']:>5} (was {b.get('candidates', '-')})  kept {n['kept']:>4} "
            f"(was {b.get('kept', '-')})  precision {n['kept'] / max(1, n['candidates']):.2f}  "
            + " ".join(f"{k} {n[k]}" for k in app.KINDS)
            + ("  BELOW" if t in failed else "")
        )
    if update:
        YIELD.write_text(json.dumps(now, indent=2) + "\n")
        return 0
    return 1 if failed else 0


def add(title: str, lang: str, index: int, label: Label) -> None:
    """Label a topic's candidate finding at `index` (0 = the largest deviation; before the decision model
    drops any) and append it to the cases: its first SHOWN quotes, as the models get them. Needs the
    database and Modal, like the server.
    """
    finding = app.compare_editions(title, lang, lambda *_: None)["differences"][index]
    app.card_order([finding])
    members = finding["members"]
    case_id = f"{title}#{index}"
    passages = [{k: m[k] for k in ("lang", "heading", "text", "sentence")} for m in members[: app.SHOWN]]
    cases = [c for c in load() if c["id"] != case_id] if CASES.exists() else []
    cases.append({"id": case_id, "label": label, "passages": passages})
    CASES.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(f"{case_id}: {label}, " + ", ".join(f"[{p['lang']}] {p['sentence'][:60]}" for p in passages))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("decide", help="the decision model's verdicts")
    commands.add_parser("explain", help="the LLM's verdicts, highlights and translations")
    commands.add_parser("embeddings", help="bge-m3 distances against FRAMING_MAX")
    yielding = commands.add_parser("yield", help="detection's yield on the reference topics, against a baseline")
    yielding.add_argument("--update", action="store_true", help="save this run as the baseline")
    adding = commands.add_parser("add", help="label a finding of a topic as a new case")
    adding.add_argument("title")
    adding.add_argument("lang")
    adding.add_argument("index", type=int)
    adding.add_argument("label", choices=LABELS)
    args = parser.parse_args()
    if args.command == "add":
        add(args.title, args.lang, args.index, args.label)
    elif args.command == "yield":
        sys.exit(yield_eval(update=args.update))
    else:
        sys.exit({"decide": decide_eval, "explain": explain_eval, "embeddings": embeddings_eval}[args.command]())


if __name__ == "__main__":
    main()
