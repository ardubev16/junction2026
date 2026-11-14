import hashlib
from functools import cache

import modal

from .db import connect
from .embed_gpu import APP, MODEL, MT, NLI

BATCH = 512  # texts per call: keeps each payload around 2 MB


@cache
def _embedder():
    return modal.Cls.from_name(APP, "Embedder")()


def _batches(items: list) -> list[list]:
    return [items[i : i + BATCH] for i in range(0, len(items), BATCH)]


def _gpu(method: str, items: list, **kwargs) -> list:
    """One of the Modal class's methods over all items, in batches."""
    return [x for batch in getattr(_embedder(), method).map(_batches(items), kwargs=kwargs) for x in batch] if items else []


def _cached(table: str, model: str, items: list, compute) -> list:
    """compute(items) for the items `table` does not have yet (keyed by sha256 of model + item, a text
    or a tuple of texts), stored there; then every item's result from the table."""
    if not items:
        return []
    keys = [hashlib.sha256("\n".join([model, *((i,) if isinstance(i, str) else i)]).encode()).digest() for i in items]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE k IN ({', '.join(['%s'] * len(keys))})", keys)
        have = dict(cur.fetchall())
        if missing := {k: i for k, i in zip(keys, items) if k not in have}:
            new = dict(zip(missing, compute(list(missing.values()))))
            cur.executemany(f"INSERT IGNORE INTO {table} VALUES (%s, %s)", list(new.items()))
            have |= new
    return [have[k] for k in keys]


def embed(texts: list[str]) -> list[bytes]:
    """bge-m3 vectors as MariaDB VECTOR values (little-endian float32), computed on a Modal H100."""
    return _gpu("embed", texts)


def embed_cached(texts: list[str]) -> list[bytes]:
    """embed() for small fixed sets of texts that every process needs (anchor sentences), kept in
    the embedding_cache table: only texts never embedded before go to the GPU."""
    return _cached("embedding_cache", MODEL, texts, embed)


def token_counts(texts: list[str]) -> list[int]:
    """bge-m3 tokens per text, special tokens included: more than 8192 means the model truncates it."""
    return _gpu("token_counts", texts)


def to_english(items: list[tuple[str, str]]) -> list[str]:
    """Each (edition code, text) machine-translated to English, kept in translation_cache."""
    return _cached("translation_cache", MT, items, lambda todo: _gpu("to_english", todo))


def contradiction(pairs: list[tuple[str, str]], model: str = NLI) -> list[float]:
    """For each (premise, hypothesis), the probability by NLI model `model` (NLI or NLI_MULTI) that
    they contradict, kept in nli_cache: a topic recomputed after a code change costs no GPU call."""
    return _cached("nli_cache", model, pairs, lambda todo: _gpu("contradiction", todo, model=model))
