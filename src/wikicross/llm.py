"""JSON-answering LLM calls, swappable between providers: LLM_API_TYPE (gemini or openai, for any
OpenAI-compatible server), LLM_URL, LLM_MODEL and LLM_API_KEY, all required (config.py); LLM_EXTRA
adds provider-specific request fields. For a new API, add a (request, text) pair to APIS.
"""

import hashlib
import json
import re
import time
from http import HTTPStatus

import httpx
from fastapi import HTTPException

from .config import settings
from .db import connect
from .telemetry import CACHE_LOOKUPS

# What the answers depend on: the cache key (the API key does not change them, so it is left out).
LLM = {"api": settings.llm_api_type, "url": settings.llm_url, "model": settings.llm_model, "extra": settings.llm_extra}


def gemini_request(system: str, user: str, schema: dict, key: str) -> tuple[str, dict[str, str], dict]:
    return (
        f"{settings.llm_url}/models/{settings.llm_model}:generateContent",
        {"x-goog-api-key": key},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": 16384,  # caps thinking + answer together
                "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": schema}},
                **settings.llm_extra,
            },
        },
    )


def gemini_text(response: dict) -> str:
    return "".join(p.get("text", "") for p in response["candidates"][0]["content"]["parts"] if not p.get("thought"))


def openai_request(system: str, user: str, schema: dict, key: str) -> tuple[str, dict[str, str], dict]:
    return (
        f"{settings.llm_url}/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {
            "model": settings.llm_model,
            "max_tokens": 16384,
            "temperature": 0,
            "messages": [
                # Not every OpenAI-compatible server enforces a schema: put it in the prompt.
                {
                    "role": "system",
                    "content": f"{system}\nReply with JSON only, matching this JSON schema: {json.dumps(schema)}",
                },
                {"role": "user", "content": user},
            ],
            **settings.llm_extra,
        },
    )


def openai_text(response: dict) -> str:
    content = response["choices"][0]["message"]["content"] or ""
    return content[content.find("{") : content.rfind("}") + 1]  # the model may wrap the JSON in a code fence


APIS = {"gemini": (gemini_request, gemini_text), "openai": (openai_request, openai_text)}


def retry_delay(error: str) -> float | None:
    """Seconds the provider asks us to wait: Gemini's RetryInfo ("retryDelay": "22s") or "retry in 22.0s"."""
    m = re.search(r'"retryDelay":\s*"([\d.]+)s"|retry in ([\d.]+)s', error)
    return float(m.group(1) or m.group(2)) if m else None


# scripts/profile.py --fresh turns this off, so a profiled topic's LLM calls are made, not read back.
READ_CACHE: bool = True
MAX_RETRY_WAIT = 60  # seconds: a longer asked-for wait is a daily quota, not worth waiting out


def chat(system: str, user: str, schema: dict) -> dict:
    """One LLM call answering JSON in `schema`, cached in MariaDB."""
    cache_key = hashlib.sha256(json.dumps([LLM, system, user, schema]).encode()).digest()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT response FROM llm_cache WHERE k = %s", (cache_key,))
        if (row := cur.fetchone()) and READ_CACHE:
            CACHE_LOOKUPS.add(1, {"cache": "llm", "result": "hit"})
            return json.loads(row[0])
        CACHE_LOOKUPS.add(1, {"cache": "llm", "result": "miss"})
        request, text = APIS[settings.llm_api_type]
        url, headers, body = request(system, user, schema, settings.llm_api_key.get_secret_value())
        for attempt in range(4):
            try:
                r = httpx.post(url, headers=headers, json=body, timeout=600)
            except httpx.HTTPError as e:
                raise HTTPException(502, f"LLM request failed: {e}") from e
            if r.status_code == HTTPStatus.SERVICE_UNAVAILABLE:  # Gemini's "high demand": frequent and short
                time.sleep(2 * (attempt + 1))
            elif (
                r.status_code == HTTPStatus.TOO_MANY_REQUESTS
                and (wait := retry_delay(r.text)) is not None
                and wait <= MAX_RETRY_WAIT
            ):
                time.sleep(wait)  # per-minute quota (Gemini free tier: 5/min); a daily quota fails at once
            else:
                break
        if r.is_error:
            try:
                message = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = r.text[:300]
            raise HTTPException(502, f"LLM error {r.status_code}: {message}")
        try:
            answer = json.loads(text(r.json()))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise HTTPException(502, f"LLM gave no JSON answer: {r.text[:300]}") from e
        cur.execute("REPLACE INTO llm_cache VALUES (%s, %s)", (cache_key, json.dumps(answer)))
        return answer
