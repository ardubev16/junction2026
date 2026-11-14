"""Download dataset S (articles + bge-m3 vectors, fi/sv/en) and load it into MariaDB."""

import hashlib
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from .db import LANGS, SCHEMA, connect

RELEASE = "https://github.com/MariaDB/mariadb-wikipedia-datasets/releases/download/s-2026-10"
DATA = Path("data")
BATCH = 200


def download(name: str, sums: dict[str, str]) -> Path:
    path = DATA / name
    if not path.exists():
        part = path.with_suffix(".part")
        with httpx.stream("GET", f"{RELEASE}/{name}", follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with part.open("wb") as f:
                for block in r.iter_bytes(1 << 20):
                    f.write(block)
        part.rename(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sums[name]:
        path.unlink()
        raise SystemExit(f"{name}: checksum mismatch, deleted; run again")
    print(f"{name}: ok", flush=True)
    return path


def insert(cur, sql: str, rows: list[tuple]) -> None:
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i : i + BATCH])


def main() -> None:
    DATA.mkdir(exist_ok=True)
    sums_text = httpx.get(f"{RELEASE}/SHA256SUMS", follow_redirects=True, timeout=60).raise_for_status().text
    sums = {name: h for h, name in (line.split() for line in sums_text.splitlines() if line)}
    conn = connect()
    cur = conn.cursor()
    for stmt in SCHEMA:
        cur.execute(stmt)
    for lang in LANGS:
        articles = pq.read_table(
            download(f"articles-{lang}.parquet", sums),
            columns=["page_id", "wikidata_id", "title", "url", "text"],
        ).to_pylist()
        insert(
            cur,
            "REPLACE INTO article VALUES (%s, %s, %s, %s, %s, %s)",
            [(lang, a["page_id"], a["wikidata_id"], a["title"], a["url"], a["text"]) for a in articles],
        )
        vectors = pq.read_table(download(f"vectors-bge-m3-{lang}.parquet", sums))
        matrix = vectors.column("embedding").combine_chunks().values.to_numpy().astype("<f4").reshape(-1, 1024)
        insert(
            cur,
            "REPLACE INTO article_vector VALUES (%s, %s, %s, %s)",
            [
                (lang, p, t, row.tobytes())
                for p, t, row in zip(
                    vectors.column("page_id").to_pylist(), vectors.column("truncated").to_pylist(), matrix
                )
            ],
        )
        print(f"{lang}: {len(articles)} articles, {len(matrix)} vectors loaded", flush=True)
