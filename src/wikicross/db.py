import os

import pymysql
import pymysql.connections
import pymysql.cursors

LANGS = ("fi", "sv", "en")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS article (
      lang        VARCHAR(12)  NOT NULL,
      page_id     INT UNSIGNED NOT NULL,
      wikidata_id VARCHAR(20),
      title       VARCHAR(255) NOT NULL,
      url         VARCHAR(500) NOT NULL,
      text        MEDIUMTEXT   NOT NULL,
      PRIMARY KEY (lang, page_id),
      KEY (wikidata_id),
      KEY (title)
    ) CHARACTER SET utf8mb4""",
    # Parts of articles, embedded on demand with the same model; HNSW finds a part's counterpart
    # in another language anywhere in the corpus.
    """CREATE TABLE IF NOT EXISTS chunk (
      lang      VARCHAR(12)       NOT NULL,
      page_id   INT UNSIGNED      NOT NULL,
      seq       SMALLINT UNSIGNED NOT NULL,
      heading   VARCHAR(500)      NOT NULL,
      text      TEXT              NOT NULL,
      embedding VECTOR(1024)      NOT NULL,
      PRIMARY KEY (lang, page_id, seq),
      VECTOR INDEX (embedding) M=16 DISTANCE=cosine
    ) CHARACTER SET utf8mb4""",
    # Sentences of those parts (seq = the part). Matched only inside a pair of parts, by an exact
    # join: cheaper than HNSW lookups there (0.11 s vs 3.7 s for Winter War), so no vector index.
    """CREATE TABLE IF NOT EXISTS sentence (
      lang      VARCHAR(12)       NOT NULL,
      page_id   INT UNSIGNED      NOT NULL,
      seq       SMALLINT UNSIGNED NOT NULL,
      n         SMALLINT UNSIGNED NOT NULL,
      text      TEXT              NOT NULL,
      embedding VECTOR(1024)      NOT NULL,
      PRIMARY KEY (lang, page_id, seq, n)
    ) CHARACTER SET utf8mb4""",
    # LLM answers (explanations), keyed by sha256 of model + prompt, and Azure Translator's (translator.py),
    # keyed by sha256 of the text.
    """CREATE TABLE IF NOT EXISTS llm_cache (
      k        BINARY(32) PRIMARY KEY,
      response MEDIUMTEXT NOT NULL
    ) CHARACTER SET utf8mb4""",
    # A row means: every edition of this topic in `scripts` (wiki.SCRIPTS) has been fetched (or ruled out).
    """CREATE TABLE IF NOT EXISTS topic_editions (
      wikidata_id VARCHAR(20)  PRIMARY KEY,
      fetched_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
      scripts     VARCHAR(100) NOT NULL DEFAULT 'LATIN'
    )""",
    # Tables made before Cyrillic was added: their rows covered Latin only.
    "ALTER TABLE topic_editions ADD COLUMN IF NOT EXISTS scripts VARCHAR(100) NOT NULL DEFAULT 'LATIN'",
    # Embeddings every process needs again (the framing axes' and the appendix headings' anchor
    # sentences), keyed by sha256 of model + text: a restart then costs no GPU call. Article passages
    # and sentences keep theirs in chunk and sentence.
    """CREATE TABLE IF NOT EXISTS embedding_cache (
      k         BINARY(32)   PRIMARY KEY,
      embedding VECTOR(1024) NOT NULL
    )""",
    # A topic's computed differences, for reloads: valid while `state` (sha256 of the comparison code
    # and the topic's editions) is unchanged.
    """CREATE TABLE IF NOT EXISTS diff_cache (
      wikidata_id VARCHAR(20) PRIMARY KEY,
      state       BINARY(32)  NOT NULL,
      response    LONGTEXT    NOT NULL
    ) CHARACTER SET utf8mb4""",
]


def widen_lang(cur: pymysql.cursors.Cursor) -> None:
    """Make lang columns created as CHAR(2) wide enough for any Wikipedia code (be-tarask). Idempotent."""
    cur.execute(
        "SELECT TABLE_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'lang' "
        "AND CHARACTER_MAXIMUM_LENGTH = 2 AND TABLE_NAME IN ('article','chunk','sentence')"
    )
    for (table,) in cur.fetchall():
        cur.execute(f"ALTER TABLE {table} MODIFY lang VARCHAR(12) NOT NULL")


def connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3308")),
        user=os.environ.get("DB_USER", "wikicross"),
        password=os.environ.get("DB_PASSWORD", "wikicross"),
        database=os.environ.get("DB_NAME", "wikicross"),
        charset="utf8mb4",
        autocommit=True,
    )
