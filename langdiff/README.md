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

No LLM is needed: three levels of bge-m3 vectors, compared in MariaDB (`compare.py`).

1. **Article** (`article`, `article_vector`): the dataset as is. Editions of a topic share a
   `wikidata_id`; their vectors give the whole-article distance.
2. **Passage** (`chunk`, HNSW index): paragraphs merged to ≥300 characters, never across a heading;
   source and link sections skipped. For each passage, its nearest passage in every other language
   over the whole corpus (`ORDER BY VEC_DISTANCE_COSINE(...) LIMIT 1`, served by the vector index),
   kept when the match is mutual and closer than 0.40. The counterpart may be in another article.
   Information only one edition has never forms such a pair, so it is not reported.
3. **Sentence** (`sentence`, no index): inside each passage pair, sentences that are each other's
   nearest. An exact join (two `ROW_NUMBER()`s): a passage pair holds a few dozen sentence pairs,
   so it beats index lookups (Winter War: 0.11 s vs 3.7 s for per-sentence HNSW).

On sentence pairs clearly about the same thing:

- **Different figures** (`discrepancy.py`): numbers each side has and the other lacks, close in
  value: quantities within a factor of 1.67, years within ±2 for very close pairs only. Thousands
  separators (`25,904`, `23 576`) are normalised; each number matches once, to its closest
  counterpart. Whole passages are compared too, for quantities only and only when they share an
  identical number ("43,557 wounded" in both shows they report the same statistics): that catches a
  table row against a sentence.
- **Different framing**: each sentence's position on semantic axes, one `VEC_DISTANCE_COSINE`
  against an axis vector. An axis is the difference between two groups of anchor sentences written
  in all three languages ("a well-documented fact" vs "an unconfirmed, disputed claim"; "praised"
  vs "condemned"), so the language cancels out. Positions are compared as z-scores against each
  language's own mean; pairs at least 1.2σ apart are reported.

Example (Urho Kekkonen): fi "Vuoden 1978 presidentinvaalit olivat riemuvoitto istuvalle
presidentille" (a triumph) vs sv "Presidentvalet år 1978 var enbart ett statspolitiskt skådespel" (a
mere political spectacle): evaluation axis, 3.0σ.

**AI summaries** (checkbox on the page, off by default): an LLM checks each finding, says what each
edition states, and can translate the quotes to English keeping the highlights. Cached in `llm_cache`.

Limits: names, places and claims that contradict without numbers or a shift in tone are not found
without the LLM. Axes are noisy on short or list-like sentences. The thresholds are tuned on two
articles (Winter War, Urho Kekkonen).

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages), `GET /api/diff?title=Talvisota&limit=15`,
`POST /api/explain {"passages": [{"lang", "heading", "text"}, {…}]}` (one pair),
`POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
