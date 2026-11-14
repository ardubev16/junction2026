# langdiff

Where do the Wikipedia editions of the same topic, in every Latin-script language, state different
facts? Built on dataset S of
[mariadb-wikipedia-datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets) (fi, sv, en) and
MariaDB Vector; the other editions are fetched live from Wikipedia the first time a topic is asked for.

## Run

Needs Docker, uv and a [Modal](https://modal.com) account (`uv run modal setup`). Passages and
sentences are embedded with bge-m3 on a Modal H100 (`src/langdiff/embed_gpu.py`).

```bash
docker compose up -d --wait   # MariaDB on 127.0.0.1:3308, data in the langdiff-data volume
uv run langdiff-load          # download S (articles + bge-m3 vectors, fi/sv/en) into MariaDB
uv run modal deploy src/langdiff/embed_gpu.py   # bge-m3 on an H100, scales to zero after 5 idle minutes
uv run --env-file .env langdiff   # http://127.0.0.1:8000; .env holds AI_API_KEY
```

`langdiff-load` keeps its downloads in `data/` (checked against the release's `SHA256SUMS`) and
can be run again. Settings by environment: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`,
`DB_NAME`.

Embedding an article the first time: ~10 s with a warm GPU container (Urho Kekkonen, fi + sv + en),
then 0.3 s from the database. A cold container first loads the model: ~30–50 s. Modal's vectors
match Ollama's `bge-m3` (cosine 0.99999), so they are comparable with the dataset's.

**Live editions** (`src/langdiff/wiki.py`): the first request for a topic follows its language links
and fetches every edition whose title and text are Latin script (≥90 % of letters), one MediaWiki API
request at a time (Wikimedia answers bursts with 429), converts the plain-text extract to Markdown
without its closing appendix (references, bibliography, links: headings classified by bge-m3 against
anchor names, only in the trailing run of sections without prose), and embeds them all in one batch.
`topic_editions` remembers finished topics. Measured: Stepan Bandera (not in S) 47 editions in 49 s,
then 4.4 s; Talvisota 52 more editions besides the dataset's fi/sv/en in 103 s. Titles not in the
database are looked up on English Wikipedia (`/api/diff?lang=` picks another).

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

No LLM is needed: articles, passages and sentences are matched across languages with bge-m3
vectors in MariaDB (HNSW for passages, an exact join for sentences), matched sentences are grouped
into one group per fact, and each group is checked for **different figures** and **different
framing** (position on "fact ↔ disputed" and "praised ↔ condemned" axes). With three editions in a
group, the one that disagrees with the other two is the outlier ("260 (fi, sv) vs 259 (en)").

Full explanation with diagrams, measured costs, tradeoffs and notes on scaling to more languages and
all of Wikipedia: [docs/how-it-works.md](docs/how-it-works.md).

**AI summaries** (checkbox on the page, off by default): an LLM checks each finding, says what each
edition states, and can translate the quotes to English keeping the highlights. Cached in `llm_cache`.

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages, then English Wikipedia's suggestions), `GET /api/diff?title=Talvisota&limit=15`,
`POST /api/explain {"passages": [{"lang", "heading", "text"}, …]}` (one finding),
`POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
