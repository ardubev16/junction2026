# langdiff

Which parts of a Wikipedia article differ the most between its Finnish, Swedish and English
versions? Built on dataset S of
[mariadb-wikipedia-datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets) and MariaDB Vector.

## Run

Needs Docker, uv and [Ollama](https://ollama.com) with `bge-m3` (`ollama pull bge-m3`).

```bash
docker compose up -d --wait   # MariaDB on 127.0.0.1:3308, data in the langdiff-data volume
uv run langdiff-load          # download S (articles + bge-m3 vectors, fi/sv/en) into MariaDB
uv run --env-file .env langdiff   # http://127.0.0.1:8000; .env holds OPENROUTER_API_KEY
```

`langdiff-load` keeps its downloads in `data/` (checked against the release's `SHA256SUMS`) and
can be run again. Settings by environment: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `OLLAMA_URL`, `LLM_URL`, `LLM_MODEL` (OpenAI-compatible; default: OpenRouter's
`nvidia/nemotron-3.5-super-vl:free`), `OPENROUTER_API_KEY`.

## How

- `article`, `article_vector`: the dataset as is — one bge-m3 vector per article. They give the
  whole-article distance between languages.
- `chunk`: an article's parts (paragraphs merged to ≥300 characters, never across a heading; source
  and link sections skipped), embedded with the same bge-m3 the first time the article is asked
  for, then cached.
- For each part, MariaDB finds the closest part in every other language
  (`VEC_DISTANCE_COSINE` + `ROW_NUMBER()`). A part's score is its largest such distance: high
  means at least one language has nothing like it.
- For each divergent part, the LLM writes a headline and a 1–2 sentence summary of what differs
  (no suggested edits), and picks the verbatim phrases carrying the difference; the UI marks them
  in the side-by-side quotes. "View quotes in English" translates a card's quotes in one LLM call,
  keeping the marks. Only English for now (`TARGETS` in `app.py`). LLM answers are cached in the
  `llm_cache` table: the free model allows 50 requests a day (1,000 with 10 credits on the account).

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages), `GET /api/diff?title=Talvisota&limit=10`,
`POST /api/explain {"passages": [{"lang", "heading", "text"}, …]}` (divergent part first),
`POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
