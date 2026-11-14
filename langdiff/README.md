# langdiff

Which parts of a Wikipedia article differ the most between its Finnish, Swedish and English
versions? Built on dataset S of
[mariadb-wikipedia-datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets) and MariaDB Vector.

## Run

Needs Docker, uv and [Ollama](https://ollama.com) with `bge-m3` (`ollama pull bge-m3`).

```bash
docker compose up -d --wait   # MariaDB on 127.0.0.1:3308, data in the langdiff-data volume
uv run langdiff-load          # download S (articles + bge-m3 vectors, fi/sv/en) into MariaDB
uv run --env-file .env langdiff   # http://127.0.0.1:8000; .env holds AI_API_KEY
```

`langdiff-load` keeps its downloads in `data/` (checked against the release's `SHA256SUMS`) and
can be run again. Settings by environment: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `OLLAMA_URL`.

### LLM

`AI_API_KEY` is the key for whichever provider is selected. `LLM_PRESET` picks one of the presets
in `src/langdiff/llm.py`; `LLM_API`, `LLM_URL`, `LLM_MODEL` override single fields of it.

| `LLM_PRESET` | API | Model |
|---|---|---|
| `gemini` (default) | Gemini `generateContent` | `gemini-4-hydrogen`, thinking level `low` |
| `verda` | OpenAI-compatible | `nemotron-3.5-super-vl` on DataCrunch (cold start: ~5 min) |
| `openrouter` | OpenAI-compatible | `nvidia/nemotron-3.5-super-vl:free` |

```bash
LLM_PRESET=verda uv run --env-file .env langdiff
LLM_PRESET=openrouter LLM_MODEL=nvidia/nemotron-3.5-super-vl uv run --env-file .env langdiff
```

A new provider with one of these APIs is a new preset; a new API is a `(request, text)` pair in
`APIS`. Answers are cached per preset in the `llm_cache` table.

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
  `llm_cache` table.

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages), `GET /api/diff?title=Talvisota&limit=10`,
`POST /api/explain {"passages": [{"lang", "heading", "text"}, …]}` (divergent part first),
`POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
