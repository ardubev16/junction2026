"""Azure AI Translator (Text API v3): the snippets a card shows in English beyond the AI's explanation
(quotes past the first three, their headings, paragraphs). Each text goes with its edition's language
(`from`), never guessed; languages Azure lacks (Frisian, Low German, Esperanto, …) fall back to the LLM,
logged and counted (telemetry.TRANSLATIONS, engine "llm") so the gaps can be found and closed.

AZURE_TRANSLATOR_KEY is the resource's key; AZURE_TRANSLATOR_REGION its region (needed for a regional or
multi-service resource, left out for a global one); AZURE_TRANSLATOR_URL overrides the endpoint.
"""

import contextvars
import functools
import hashlib
import html
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus

import httpx
from fastapi import HTTPException

from . import llm
from .config import settings
from .db import connect
from .telemetry import CACHE_LOOKUPS, TRANSLATIONS

log = logging.getLogger(__name__)
URL = settings.azure_translator_url
MAX_ITEMS, MAX_CHARS = 1000, 50_000  # per request (Azure's limits)
BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
CYRILLIC = re.compile("[\u0400-\u04ff]")
ALIASES = {"tl": "fil", "mn": "mn-Cyrl"}  # Wikipedia's code -> Azure's, where they differ


@functools.cache
def azure_languages() -> frozenset[str]:
    """The languages Azure translates from (no key needed); fetched once per process."""
    try:
        r = httpx.get(f"{URL}/languages", params={"api-version": "3.0", "scope": "translation"}, timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(HTTPStatus.BAD_GATEWAY, f"Translator languages unavailable: {e}") from e
    return frozenset(r.json()["translation"])


def azure_code(lang: str, text: str) -> str | None:
    """Azure's code for a Wikipedia edition's language, or None if Azure lacks it."""
    if lang == "sr":  # Serbian Wikipedia mixes scripts; Azure wants one
        return "sr-Cyrl" if CYRILLIC.search(text) else "sr-Latn"
    code = ALIASES.get(lang, lang)
    if code in azure_languages():
        return code
    base = lang.split("-", maxsplit=1)[0]  # be-tarask -> be
    return base if base != lang and base in azure_languages() else None


def as_html(text: str) -> str:
    """Text with <mark>…</mark> highlights as HTML: everything else escaped, line breaks as <br>."""
    escaped = html.escape(text, quote=False).replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")
    return escaped.replace("\n", "<br>")


def from_html(text: str) -> str:
    return html.unescape(BR.sub("\n", text))


def azure(code: str, texts: list[str]) -> list[str]:
    """Texts of one language (Azure's `code`) in English, in as few requests as Azure's limits allow;
    sent as HTML so a <mark> highlight lands on the matching English words.
    """
    if not (key := settings.azure_translator_key):
        raise HTTPException(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "AZURE_TRANSLATOR_KEY not set: start with  uv run --env-file .env wikicross",
        )
    headers = {"Ocp-Apim-Subscription-Key": key.get_secret_value()}
    if region := settings.azure_translator_region:
        headers["Ocp-Apim-Subscription-Region"] = region
    batches: list[list[str]] = [[]]
    for item in map(as_html, texts):
        batch = batches[-1]
        if batch and (len(batch) == MAX_ITEMS or sum(map(len, batch)) + len(item) > MAX_CHARS):
            batches.append(batch := [])
        batch.append(item)
    out = []
    for batch in batches:
        try:
            r = httpx.post(
                f"{URL}/translate",
                params={"api-version": "3.0", "from": code, "to": "en", "textType": "html"},
                headers=headers,
                json=[{"Text": t} for t in batch],
                timeout=60,
            )
        except httpx.HTTPError as e:
            raise HTTPException(HTTPStatus.BAD_GATEWAY, f"Translator request failed: {e}") from e
        if r.is_error:
            try:
                message = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = r.text[:300]
            raise HTTPException(HTTPStatus.BAD_GATEWAY, f"Translator error {r.status_code}: {message}")
        out += [from_html(answer["translations"][0]["text"]) for answer in r.json()]
    return out


def by_llm(items: list[tuple[str, str]]) -> list[str]:
    """(lang, text) pairs in English by the LLM, in one call: for languages Azure lacks."""
    todo = {f"{lang}-{i}": text for i, (lang, text) in enumerate(items)}
    answer = llm.chat(
        "Translate each value of the user's JSON object to English; each key starts with the "
        "value's source language code. Keep line breaks and Markdown list markers. "
        "Text between <mark> and </mark> is highlighted: "
        "put <mark> and </mark> around the words of your translation that correspond. "
        "Reply with an object with the same keys, values translated.",
        json.dumps(todo, ensure_ascii=False),
        {"type": "object", "properties": {k: {"type": "string"} for k in todo}, "required": list(todo)},
    )
    return [str(answer.get(k, t)) for k, t in todo.items()]


def translate_all(items: list[tuple[str, str]]) -> list[str]:
    """(lang, text) pairs in English: one Azure request per language, the LLM for the languages Azure
    lacks, all at once.
    """
    groups: dict[str | None, list[int]] = {}
    for i, (lang, text) in enumerate(items):
        groups.setdefault(azure_code(lang, text), []).append(i)
    if missing := groups.get(None):
        langs = sorted({items[i][0] for i in missing})
        log.warning("Azure Translator lacks %s: %d texts translated by the LLM", ", ".join(langs), len(missing))
    out: list[str] = [""] * len(items)

    def run(code: str | None, indices: list[int]) -> None:
        texts = [items[i][1] for i in indices]
        english = by_llm([items[i] for i in indices]) if code is None else azure(code, texts)
        for i, t in zip(indices, english, strict=True):
            out[i] = t
            TRANSLATIONS.add(1, {"engine": "llm" if code is None else "azure", "lang": items[i][0]})

    # A context per call: each carries the request's trace span.
    with ThreadPoolExecutor(len(groups)) as pool:
        jobs = [pool.submit(contextvars.copy_context().run, run, code, ix) for code, ix in groups.items()]
        for job in jobs:
            job.result()
    return out


def to_english(items: list[tuple[str, str]]) -> list[str]:
    """(lang, text) pairs in English, <mark>…</mark> highlights kept on the matching words; cached per
    text in llm_cache, so showing more quotes only pays for the new ones.
    """
    keys = [hashlib.sha256(json.dumps(["azure-translator", lang, t]).encode()).digest() for lang, t in items]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT k, response FROM llm_cache WHERE k IN ({', '.join(['%s'] * len(keys))})", keys)
        known = {bytes(k): json.loads(r) for k, r in cur.fetchall()} if llm.READ_CACHE else {}
        todo = list({k: i for i, k in enumerate(keys) if k not in known}.values())  # one of each
        CACHE_LOOKUPS.add(len(keys) - len(todo), {"cache": "translator", "result": "hit"})
        CACHE_LOOKUPS.add(len(todo), {"cache": "translator", "result": "miss"})
        if todo:
            for i, english in zip(todo, translate_all([items[i] for i in todo]), strict=True):
                known[keys[i]] = english
                cur.execute("REPLACE INTO llm_cache VALUES (%s, %s)", (keys[i], json.dumps(english)))
    return [known[k] for k in keys]
