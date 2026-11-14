# langdiff

Where do the Finnish, Swedish and English Wikipedia articles on the same topic frame things
differently, or state very different figures? Built on dataset S of
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

### Chrome extension

`extension/` shows the same findings on Wikipedia itself (fi, sv, en): a "langdiff · N" button opens
a panel listing what this edition states differently from the others, with the other editions'
sentences and links to them. **Clicking a finding
shows it on the page**: in the article view and VisualEditor its paragraph is highlighted and
scrolled to; in the source editor the figure (for a value) or the whole paragraph (for framing) is
selected in the wikitext.

1. Start the backend (above) on `http://127.0.0.1:8000`.
2. `chrome://extensions` → Developer mode → **Load unpacked** → select `langdiff/extension`.
3. Open an article, e.g. `https://fi.wikipedia.org/wiki/Talvisota`, and click the button; or its
   edit view, where it loads at once.

In the article view the extension asks the backend only when the button is clicked, so reading
Wikipedia does not embed every article visited; pages that are not in the dataset get no button.
It calls the backend from its service worker (host permission, no CORS change needed); for another
backend address, change `BACKEND` in `extension/background.js` and `host_permissions` in
`extension/manifest.json`. Findings come from the dataset snapshot, not the live page: a paragraph
edited since may still be found (by its words), or not. An article not embedded yet takes minutes
the first time; past about five minutes Chrome may stop the service worker, and asking again shows
the result once the backend has finished. After changing `background.js`, reload the extension in
`chrome://extensions`: Chrome keeps running the old worker otherwise.

The web app and the extension must stay in sync: see [AGENTS.md](AGENTS.md).

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
into one group per fact, and each group is checked for **different framing** (position on "fact ↔
disputed" and "praised ↔ condemned" axes) and **very different figures** (at least 20% apart; small
differences and years are left out). With three editions in a group, the one that disagrees with
the other two is the outlier.

Full explanation with diagrams, measured costs, tradeoffs and notes on scaling to more languages and
all of Wikipedia: [docs/how-it-works.md](docs/how-it-works.md).

**AI summaries** (checkbox on the page, off by default): an LLM checks each finding, says what each
edition states, and can translate the quotes to English keeping the highlights. Cached in `llm_cache`.

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages), `GET /api/diff?title=Talvisota&limit=15`
(`differences`: values, then framing), `GET /api/context?lang=fi&page_id=…&seq=…&n=…&direction=up&count=3`
(sentences around a quote), `POST /api/explain {"passages": [{"lang", "heading", "text"}, …]}` (one
finding), `POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
