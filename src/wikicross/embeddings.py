import hashlib
from functools import cache

import modal

from .db import connect
from .embed_gpu import APP, MODEL

BATCH = 512  # texts per call: keeps each payload around 2 MB


@cache
def _embedder():
    return modal.Cls.from_name(APP, "Embedder")()


def _batches(texts: list[str]) -> list[list[str]]:
    return [texts[i : i + BATCH] for i in range(0, len(texts), BATCH)]


def embed(texts: list[str]) -> list[bytes]:
    """bge-m3 vectors as MariaDB VECTOR values (little-endian float32), computed on a Modal H100."""
    if not texts:
        return []
    return [v for batch in _embedder().embed.map(_batches(texts)) for v in batch]


def embed_cached(texts: list[str]) -> list[bytes]:
    """embed() for small fixed sets of texts that every process needs (anchor sentences), kept in
    the embedding_cache table: only texts never embedded before go to the GPU."""
    keys = [hashlib.sha256(f"{MODEL}\n{t}".encode()).digest() for t in texts]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT k, embedding FROM embedding_cache WHERE k IN ({', '.join(['%s'] * len(keys))})", keys)
        have = dict(cur.fetchall())
        missing = {k: t for k, t in zip(keys, texts) if k not in have}
        if missing:
            have |= dict(zip(missing, embed(list(missing.values()))))
            cur.executemany("INSERT IGNORE INTO embedding_cache VALUES (%s, %s)", [(k, have[k]) for k in missing])
    return [have[k] for k in keys]
