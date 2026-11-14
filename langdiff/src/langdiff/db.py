import os

import pymysql

LANGS = ("fi", "sv", "en")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS article (
      lang        CHAR(2)      NOT NULL,
      page_id     INT UNSIGNED NOT NULL,
      wikidata_id VARCHAR(20),
      title       VARCHAR(255) NOT NULL,
      url         VARCHAR(500) NOT NULL,
      text        MEDIUMTEXT   NOT NULL,
      PRIMARY KEY (lang, page_id),
      KEY (wikidata_id),
      KEY (title)
    ) CHARACTER SET utf8mb4""",
    # The downloaded bge-m3 vectors: one per article, all three languages.
    """CREATE TABLE IF NOT EXISTS article_vector (
      lang      CHAR(2)      NOT NULL,
      page_id   INT UNSIGNED NOT NULL,
      truncated BOOL         NOT NULL,
      embedding VECTOR(1024) NOT NULL,
      PRIMARY KEY (lang, page_id),
      VECTOR INDEX (embedding) M=16 DISTANCE=cosine
    )""",
    # Parts of articles, embedded on demand with the same model; a cache filled by the API.
    """CREATE TABLE IF NOT EXISTS chunk (
      lang      CHAR(2)           NOT NULL,
      page_id   INT UNSIGNED      NOT NULL,
      seq       SMALLINT UNSIGNED NOT NULL,
      heading   VARCHAR(500)      NOT NULL,
      text      TEXT              NOT NULL,
      embedding VECTOR(1024)      NOT NULL,
      PRIMARY KEY (lang, page_id, seq)
    ) CHARACTER SET utf8mb4""",
    # LLM answers (summaries, translations), keyed by sha256 of model + prompt.
    """CREATE TABLE IF NOT EXISTS llm_cache (
      k        BINARY(32) PRIMARY KEY,
      response MEDIUMTEXT NOT NULL
    ) CHARACTER SET utf8mb4""",
]


def connect():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3308")),
        user=os.environ.get("DB_USER", "langdiff"),
        password=os.environ.get("DB_PASSWORD", "langdiff"),
        database=os.environ.get("DB_NAME", "langdiff"),
        charset="utf8mb4",
        autocommit=True,
    )
