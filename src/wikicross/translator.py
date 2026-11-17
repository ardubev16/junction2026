"""Azure AI Translator (Text API v3): the snippets a card shows in English beyond the AI's explanation
(quotes past the first three, their headings, paragraphs).

AZURE_TRANSLATOR_KEY is the resource's key; AZURE_TRANSLATOR_REGION its region (needed for a regional or
multi-service resource, left out for a global one); AZURE_TRANSLATOR_URL overrides the endpoint.
"""

import hashlib
import html
import json
import os
import re
from http import HTTPStatus

import httpx
from fastapi import HTTPException

from . import llm
from .db import connect
from .telemetry import CACHE_LOOKUPS

URL = os.environ.get("AZURE_TRANSLATOR_URL", "https://api.cognitive.microsofttranslator.com")
MAX_ITEMS, MAX_CHARS = 1000, 50_000  # per request (Azure's limits)
BR = re.compile(r"<br\s*/?>", re.IGNORECASE)


def as_html(text: str) -> str:
    """Text with <mark>…</mark> highlights as HTML: everything else escaped, line breaks as <br>."""
    escaped = html.escape(text, quote=False).replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")
    return escaped.replace("\n", "<br>")


def from_html(text: str) -> str:
    return html.unescape(BR.sub("\n", text))


def request(texts: list[str]) -> list[str]:
    """The texts in English, in as few requests as Azure's limits allow. Their language is detected:
    shortcut: one request mixes many editions; a short text detected as English stays as it is.
    """
    if not (key := os.environ.get("AZURE_TRANSLATOR_KEY")):
        raise HTTPException(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "AZURE_TRANSLATOR_KEY not set: start with  uv run --env-file .env wikicross",
        )
    headers = {"Ocp-Apim-Subscription-Key": key}
    if region := os.environ.get("AZURE_TRANSLATOR_REGION"):
        headers["Ocp-Apim-Subscription-Region"] = region
    items = [as_html(t) for t in texts]
    batches: list[list[str]] = [[]]
    for item in items:
        batch = batches[-1]
        if batch and (len(batch) == MAX_ITEMS or sum(map(len, batch)) + len(item) > MAX_CHARS):
            batches.append(batch := [])
        batch.append(item)
    out = []
    for batch in batches:
        try:
            r = httpx.post(
                f"{URL}/translate",
                params={"api-version": "3.0", "to": "en", "textType": "html"},
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


def to_english(texts: list[str]) -> list[str]:
    """Each text in English, <mark>…</mark> highlights kept on the matching words; cached per text in
    llm_cache, so showing more quotes only pays for the new ones.
    """
    keys = [hashlib.sha256(json.dumps(["azure-translator", t]).encode()).digest() for t in texts]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT k, response FROM llm_cache WHERE k IN ({', '.join(['%s'] * len(keys))})", keys)
        known = {bytes(k): json.loads(r) for k, r in cur.fetchall()} if llm.READ_CACHE else {}
        todo = list({k: i for i, k in enumerate(keys) if k not in known}.values())  # one of each
        CACHE_LOOKUPS.add(len(keys) - len(todo), {"cache": "translator", "result": "hit"})
        CACHE_LOOKUPS.add(len(todo), {"cache": "translator", "result": "miss"})
        if todo:
            for i, english in zip(todo, request([texts[i] for i in todo]), strict=True):
                known[keys[i]] = english
                cur.execute("REPLACE INTO llm_cache VALUES (%s, %s)", (keys[i], json.dumps(english)))
    return [known[k] for k in keys]
