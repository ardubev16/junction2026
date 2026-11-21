"""Which findings are real disagreements: a decision model (DECISION_*: OpenRouter's Decisions API,
https://openrouter.ai/docs/guides/features/decisions) judges each finding's quotes, as its card shows
them, with two typed questions: its `kind` (factual, bias, framing, or none: not a disagreement) and its
`strength`, with calibrated probabilities. No text is generated: ~0.5 s for a batch of findings.
Answers are cached per finding in llm_cache. Measured on labelled findings: `python -m wikicross.evals decide`.
"""

import contextvars
import hashlib
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from typing import cast

import httpx

from . import llm
from .config import settings
from .db import connect

KINDS = ("factual", "bias", "framing")  # app.KINDS: the kinds of a real disagreement
NONE = "none"
KIND = (
    "Quotes from different language editions of Wikipedia about one topic, each prefixed by its language "
    "code. Do they disagree about one same specific thing, and how?"
)
CRITERIA = {
    "factual": "They state facts about one same thing that cannot all be true: numbers, dates, names, places, "
    "outcomes, causes, who did what.",
    "bias": "About one same thing, one is clearly more favourable or critical than another, or uses loaded, "
    "emotive words where another is neutral.",
    "framing": "The same facts about one same thing, presented differently: settled in one, disputed or "
    "attributed in another.",
    NONE: "No disagreement: they state different things, even about the same place, project or company (e.g. "
    "one a number of employees, another of data centres; one an investment, another a total budget), one only "
    "adds detail, or they agree.",
}
STRENGTH = "How much would a reader comparing these editions care about this difference?"
LEVELS = [
    "Minor: a small detail, rounding, or a slightly different emphasis",
    "Notable: a clear difference about something the article states",
    "Major: a central fact, judgement or event of the topic",
]
# With three quotes or more: whose quote differs. The axis's outlier measures tone, not facts. (A separate
# "same specific thing?" question was tried and dropped: docs/experiments/2026-11-decision-model.md.)
OUTLIER = "Which edition's quote stands apart from the others about the thing they share?"
NO_OUTLIER = "No single edition stands apart: they all differ, or none does."
MIN_OUTLIER = 3  # quotes needed to ask for an outlier (compare.MIN_OUTLIER)
BATCH = 10  # findings per request: answers stay per finding (checked on 3), fewer round trips
WORKERS = 8  # requests at once (40 in 3 s met no rate limit)
RETRIES = 3

# What an answer depends on: the cache key (the API key does not change it, so it is left out).
QUESTIONS = [
    settings.decision_url,
    settings.decision_model,
    [KIND, CRITERIA, STRENGTH, LEVELS, OUTLIER, NO_OUTLIER],
]


def lines(quotes: list[dict]) -> list[str]:
    return [f"[{q['lang']}] {q['sentence']}" for q in quotes]


def key(quotes: list[dict]) -> bytes:
    return hashlib.sha256(json.dumps([QUESTIONS, lines(quotes)]).encode()).digest()


def outliers(quotes: list[dict]) -> dict[str, str]:
    """The outlier question's options: each quote's language, and NONE."""
    return {q["lang"]: f"The [{q['lang']}] quote differs from the others, which agree." for q in quotes} | {
        NONE: NO_OUTLIER
    }


def read(answers: dict, i: int, quotes: list[dict]) -> dict | None:
    """Finding i's decision from a batch's answers: `kind` (KINDS or NONE), `real` (1 - P(none)),
    `strength` (0-2) and `outlier` (a quote's language, or None), or None if a question was refused or
    malformed.
    """
    kind, strength = answers.get(f"kind_{i}") or {}, answers.get(f"strength_{i}") or {}
    outlier = answers.get(f"outlier_{i}") or {}
    probabilities = kind.get("probabilities") or {}
    if kind.get("choice") not in (*KINDS, NONE) or not isinstance(strength.get("score"), int | float):
        return None
    asked = len(quotes) >= MIN_OUTLIER
    if asked and outlier.get("choice") not in outliers(quotes):
        return None
    return {
        "kind": kind["choice"],
        "real": round(1 - float(probabilities.get(NONE, kind["choice"] == NONE)), 4),
        "strength": round(float(strength["score"]), 3),
        "outlier": outlier["choice"] if asked and outlier["choice"] != NONE else None,
    }


def kept(d: dict) -> bool:
    """A decision that is a real disagreement."""
    return d["kind"] != NONE


def ask(batch: list[list[dict]]) -> list[dict | None]:
    """One request for up to BATCH findings (each its quotes: lang, sentence); raises RuntimeError."""
    questions: dict[str, dict] = {}
    for i, quotes in enumerate(batch):
        about = f"About f{i} only. "
        questions[f"kind_{i}"] = {"type": "choice", "instructions": about + KIND, "criteria": CRITERIA}
        questions[f"strength_{i}"] = {"type": "score", "instructions": about + STRENGTH, "criteria": LEVELS}
        if len(quotes) >= MIN_OUTLIER:
            questions[f"outlier_{i}"] = {
                "type": "choice",
                "instructions": about + OUTLIER,
                "criteria": outliers(quotes),
            }
    body = {
        "model": settings.decision_model,
        "state": {f"f{i}": lines(quotes) for i, quotes in enumerate(batch)},
        "questions": questions,
    }
    headers = {"Authorization": f"Bearer {settings.decision_api_key.get_secret_value()}"}
    for attempt in range(RETRIES + 1):
        try:
            r = httpx.post(settings.decision_url, headers=headers, json=body, timeout=60)
        except httpx.HTTPError as e:
            raise RuntimeError(f"decision request failed: {e!r}") from e
        retry = r.status_code == HTTPStatus.TOO_MANY_REQUESTS or r.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
        if not retry or attempt == RETRIES:
            break
        after = r.headers.get("retry-after", "")
        time.sleep(min(int(after) if after.isdigit() else 2 ** (attempt + 1), 30))
    if r.is_error:
        raise RuntimeError(f"decision model error {r.status_code}: {r.text[:300]}")
    answers = r.json().get("answers") or {}
    return [read(answers, i, quotes) for i, quotes in enumerate(batch)]


def decide(findings: list[list[dict]], progress: Callable[[int, int], None]) -> tuple[list[dict | None], str | None]:
    """A decision (see read()) for each finding, given as the quotes its card shows (lang, sentence), and the
    first error if some could not be asked (those are None). Cached answers are read back in one query;
    progress(done, total) follows the rest.
    """
    keys = [key(quotes) for quotes in findings]
    out: list[dict | None] = [None] * len(findings)
    with connect() as conn, conn.cursor() as cur:
        if keys and llm.READ_CACHE:
            cur.execute(f"SELECT k, response FROM llm_cache WHERE k IN ({', '.join(['%s'] * len(keys))})", keys)
            cached = {k: json.loads(v) for k, v in cur.fetchall()}
            out = [cached.get(k) for k in keys]
        todo = [i for i, d in enumerate(out) if d is None]
        batches = [todo[s : s + BATCH] for s in range(0, len(todo), BATCH)]
        error, done = None, len(findings) - len(todo)
        progress(done, len(findings))
        with ThreadPoolExecutor(WORKERS) as pool:
            # A context per request: each carries the "decide" step's trace span.
            jobs = {pool.submit(contextvars.copy_context().run, ask, [findings[i] for i in b]): b for b in batches}
            for job in as_completed(jobs):
                try:
                    answers = cast("list[dict | None]", job.result())  # Context.run hides ask()'s type
                except RuntimeError as e:
                    error = error or str(e)
                    continue
                for i, d in zip(jobs[job], answers, strict=True):
                    out[i] = d
                    if d is not None:
                        cur.execute("REPLACE INTO llm_cache VALUES (%s, %s)", (keys[i], json.dumps(d)))
                done += len(jobs[job])
                progress(done, len(findings))
    return out, error
