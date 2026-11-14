from functools import cache

import modal

from .embed_gpu import APP

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


def token_counts(texts: list[str]) -> list[int]:
    """bge-m3 tokens per text, special tokens included: more than 8192 means the model truncates it."""
    if not texts:
        return []
    return [n for batch in _embedder().token_counts.map(_batches(texts)) for n in batch]
