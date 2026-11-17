"""JSON-answering LLM calls, swappable between providers.

Pick a preset with LLM_PRESET (default: verda); LLM_API, LLM_URL, LLM_MODEL override single fields.
Each preset reads its key from its own variable (`key`), falling back to AI_API_KEY, so keys for
several providers can sit in .env together. To add a provider speaking an API already here, add a
preset; for a new API, add a (request, text) pair to APIS.
"""

import hashlib
import json
import os
import re
import time

import httpx
from fastapi import HTTPException

from .db import connect
from .telemetry import CACHE_LOOKUPS

PRESETS = {
    "gemini": {
        "api": "gemini",
        "key": "GEMINI_API_KEY",
        "url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-4-hydrogen",
        # low | medium | high | xhigh: low is enough for summaries and translations, and fastest.
        "extra": {"thinkingConfig": {"thinkingLevel": "low"}},
    },
    "verda": {
        "api": "openai",
        "key": "VERDA_API_KEY",
        "url": "https://inference.verda.com/v1",
        "model": "kimi-k3-1-pro",
        "extra": {},
    },
    "openrouter": {
        "api": "openai",
        "key": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1",
        "model": "nvidia/nemotron-3.5-super-vl:free",
        "extra": {"reasoning": {"enabled": False}},  # same quality here, ~0.8 s instead of ~7 s
    },
    "minimax": {
        "api": "openai",
        "key": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1",
        "model": "minimax/minimax-m3.1-flash",  # the :free variant was retired on 2026-10-22
        "extra": {},
    },
}
LLM = PRESETS[os.environ.get("LLM_PRESET", "verda")] | {
    field: value for field in ("api", "url", "model") if (value := os.environ.get(f"LLM_{field.upper()}"))
}


def gemini_request(system: str, user: str, schema: dict, key: str):
    return (
        f"{LLM['url']}/models/{LLM['model']}:generateContent",
        {"x-goog-api-key": key},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": 16384,  # caps thinking + answer together
                "responseFormat": {"text": {"mimeType": "APPLICATION_JSON", "schema": schema}},
                **LLM["extra"],
            },
        },
    )


def gemini_text(response: dict) -> str:
    return "".join(p.get("text", "") for p in response["candidates"][0]["content"]["parts"] if not p.get("thought"))


def openai_request(system: str, user: str, schema: dict, key: str):
    return (
        f"{LLM['url']}/chat/completions",
        {"Authorization": f"Bearer {key}"},
        {
            "model": LLM["model"],
            "max_tokens": 16384,
            "temperature": 0,
            "messages": [
                # Not every OpenAI-compatible server enforces a schema: put it in the prompt.
                {"role": "system", "content": f"{system}\nReply with JSON only, matching this JSON schema: {json.dumps(schema)}"},
                {"role": "user", "content": user},
            ],
            **LLM["extra"],
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


def chat(system: str, user: str, schema: dict) -> dict:
    """One LLM call answering JSON in `schema`, cached in MariaDB."""
    # Which variable holds the key does not change the answer: keep it out of the cache key.
    cache_key = hashlib.sha256(
        json.dumps([{k: v for k, v in LLM.items() if k != "key"}, system, user, schema]).encode()
    ).digest()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT response FROM llm_cache WHERE k = %s", (cache_key,))
        if row := cur.fetchone():
            CACHE_LOOKUPS.add(1, {"cache": "llm", "result": "hit"})
            return json.loads(row[0])
        CACHE_LOOKUPS.add(1, {"cache": "llm", "result": "miss"})
        api_key = os.environ.get(LLM["key"]) or os.environ.get("AI_API_KEY")
        if not api_key:
            raise HTTPException(503, f"{LLM['key']} (or AI_API_KEY) not set: start with  uv run --env-file .env wikicross")
        request, text = APIS[LLM["api"]]
        url, headers, body = request(system, user, schema, api_key)
        for attempt in range(4):
            try:
                r = httpx.post(url, headers=headers, json=body, timeout=600)
            except httpx.HTTPError as e:
                raise HTTPException(502, f"LLM request failed: {e}") from e
            if r.status_code == 503:  # Gemini's "high demand": frequent and short
                time.sleep(2 * (attempt + 1))
            elif r.status_code == 429 and (wait := retry_delay(r.text)) is not None and wait <= 60:
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
