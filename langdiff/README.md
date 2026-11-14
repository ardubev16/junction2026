# langdiff

Where do the Finnish, Swedish and English Wikipedia articles on the same topic state different
facts? Built on dataset S of
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

`LLM_PRESET` picks one of the presets in `src/langdiff/llm.py`; `LLM_API`, `LLM_URL`, `LLM_MODEL`
override single fields of it. Each preset reads its own key variable, falling back to `AI_API_KEY`,
so keys for several providers can sit in `.env` together.

| `LLM_PRESET` | API | Model | Key | Measured |
|---|---|---|---|---|
| `gemini` (default) | Gemini `generateContent` | `gemini-4-hydrogen`, thinking `low` | `GEMINI_API_KEY` | free tier: 5 requests/min, 20/day; frequent 503 "high demand" |
| `minimax` | OpenAI-compatible (OpenRouter) | `minimax/minimax-m3.1-flash` (paid; `:free` retired) | `OPENROUTER_API_KEY` | 10 summaries in 15 s |
| `openrouter` | OpenAI-compatible | `nvidia/nemotron-3.5-super-vl:free` | `OPENROUTER_API_KEY` | free: 50 requests/day |
| `verda` | OpenAI-compatible | `nemotron-3.5-super-vl` on DataCrunch | `VERDA_API_KEY` | cold start ~5 min |

```bash
LLM_PRESET=minimax uv run --env-file .env langdiff
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
- **Same subject:** for each pair of languages, MariaDB pairs up parts that are each other's nearest
  part (`VEC_DISTANCE_COSINE` + two `ROW_NUMBER()`s) and closer than `SAME_SUBJECT` (0.35).
  Information only one edition has never forms such a pair, so it is not reported.
- **Different facts:** within a pair, numbers that each side has and the other lacks, and that are
  close in value (`discrepancy.py`): quantities within a factor of 1.67, years within ±2 (years only
  for pairs closer than 0.3, since unrelated events have unrelated years). Digits read the same in
  all three languages; thousands separators (`25,904`, `23 576`) are normalised. Each number is
  matched once, to its closest counterpart. Pairs are ranked by how many figures differ.
- **AI summaries** (checkbox on the page, off by default): the LLM checks each pair for a real
  contradiction, says what each edition states, highlights the phrases, and can translate the
  quotes to English keeping the highlights. Answers are cached in the `llm_cache` table.

Limits: only figures and dates are compared without the LLM: names, places and claims need it.
A number can match a different fact in the other passage (two troop counts in one paragraph).

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages), `GET /api/diff?title=Talvisota&limit=15`,
`POST /api/explain {"passages": [{"lang", "heading", "text"}, {…}]}` (one pair),
`POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
