import os

import httpx
import numpy as np

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = "bge-m3"  # the model the dataset's vectors were made with


def embed(texts: list[str]) -> list[bytes]:
    """bge-m3 vectors as MariaDB VECTOR values (little-endian float32)."""
    out = []
    for i in range(0, len(texts), 32):
        r = httpx.post(
            f"{OLLAMA}/api/embed",
            json={"model": MODEL, "input": texts[i : i + 32], "truncate": True},
            timeout=600,
        )
        r.raise_for_status()
        out += [np.asarray(v, "<f4").tobytes() for v in r.json()["embeddings"]]
    return out
