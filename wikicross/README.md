# WikiCross

Where do all the Wikipedia versions of an article frame things differently? They are fetched live
from Wikipedia the first time an article is asked for, embedded with bge-m3 and compared in MariaDB
Vector.

## Run

Needs Docker, uv and a [Modal](https://modal.com) account (`uv run modal setup`). Passages and
sentences are embedded with bge-m3 on a Modal H100 (`src/wikicross/embed_gpu.py`).
The embedder is looked up by name in the active Modal profile's workspace; to use one already
deployed elsewhere (the team's is in `fabio-missagia`), add a token for that workspace instead of
deploying: `uv run modal token new --profile fabio-missagia` (pick the workspace in the browser; it
becomes the active profile), or set `MODAL_PROFILE=fabio-missagia` when starting the server.

```bash
docker compose up -d --wait   # MariaDB on 127.0.0.1:3308, data in the wikicross-data volume
uv run modal deploy src/wikicross/embed_gpu.py   # bge-m3 on an H100, scales to zero after 5 idle minutes
uv run --env-file .env wikicross   # http://127.0.0.1:8000; .env holds AI_API_KEY
```

The server creates its tables on start; the database fills as topics are asked for. Settings by
environment: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.

Embedding an article the first time: ~10 s with a warm GPU container (Urho Kekkonen, fi + sv + en),
then 0.3 s from the database. A cold container first loads the model: ~30–50 s. Modal's vectors
match Ollama's `bge-m3` (cosine 0.99999).

**Live editions** (`src/wikicross/wiki.py`): the first request for a topic follows its language links
and fetches every edition whose title and text are in Latin or Cyrillic script (≥90 % of letters;
`SCRIPTS`), eight MediaWiki API requests at a time (`FETCHERS`; 429 answers are waited out), converts the
plain-text extract to Markdown without its closing appendix (references, bibliography, links:
headings classified by bge-m3 against anchor names in Latin and Cyrillic languages, only in the
trailing run of sections without prose), and embeds them all in one batch. `topic_editions`
remembers finished topics and which scripts they covered, so a topic fetched before Cyrillic was
added fetches its Cyrillic editions once. Measured, one request at a time: Stepan Bandera
47 editions in 49 s; Talvisota 52 editions besides fi/sv/en (then already in the database) in 103 s. Eight at a
time: Mannerheim-linja's 28 editions in about 1 s. Adding Cyrillic,
Urho Kekkonen gained 8 editions (be, be-tarask, mn, os, ru, sr, uk, …) and Talvisota went to 66.
Titles are looked up in any language in the database, else on English Wikipedia; `/api/diff?lang=de`
looks them up in that edition only (in the database, else on de.wikipedia.org), as the extension does.

**Loading feedback**: while `/api/diff` works, `/api/progress?title=` gives its current stage
("Fetching edition 12 of 63 from Wikipedia (ru.wikipedia.org)", embedding, matching, comparing) and
the seconds so far; the web app and the extension poll it each second under a spinner. AI checks and
translations show the same spinner.

**Caches in MariaDB**: everything computed once is kept, so a reload or a server restart repeats no
work. Passage and sentence vectors live in `chunk` and `sentence`, the editions in `article` /
`article_vector` (`topic_editions` marks a topic fetched), the anchor sentences of the framing axes and
of the appendix headings in `embedding_cache`, LLM answers in `llm_cache`, and each topic's computed
differences in `diff_cache`, valid while its editions, the comparison code (`compare.py`) and the
model (`embed_gpu.py`) are unchanged. Measured: Talvisota (66 editions) 43.9 s the first time, 0.29 s on
reload, 0.13 s after a restart; Urho Kekkonen 13.7 s, then 0.13 s. A topic loaded later can change a
passage match of a cached topic (passages are matched over the whole corpus): delete its `diff_cache`
row to recompute.

### Public deployment (HTTPS)

`docker-compose.yml`'s `deploy` profile adds the app (`Dockerfile`) and Caddy (stock `caddy:2` image,
configured by `Caddyfile`) in front of it, on ports 80 and 443. Caddy gets a Let's Encrypt certificate for
the domain by itself and renews it (kept in the `caddy-data` volume). On the VM: point the
domain's A record at it (DNS only, no proxy in front; no AAAA record, see below), open ports 80 and
443 (TCP, and 443 UDP for HTTP/3), then:

```bash
cat >> .env <<'EOF'
COMPOSE_PROFILES=deploy
DOMAIN=wikicross.example.com
ALLOWED_IPS=198.51.100.23     # not rate-limited (the event network): IPs or CIDR ranges, space-separated
MODAL_TOKEN_ID=ak-…           # `uv run modal token new` or modal.com/settings/tokens
MODAL_TOKEN_SECRET=as-…
EOF
docker compose up -d --build --wait
```

The database starts empty and fills as topics are asked for. To keep the topics computed so far,
copy the database instead: `docker compose exec mariadb mariadb-dump -uwikicross -pwikicross wikicross
| gzip > wikicross.sql.gz` here, `gunzip -c wikicross.sql.gz | docker compose exec -T mariadb mariadb
-uwikicross -pwikicross wikicross` there.

**Rate limit** (`app.py`, `LIMITS`; stated on the home page): anyone can use it, but a client outside
`ALLOWED_IPS` gets 60 `/api/` requests a minute and 30 for `/api/explain` + `/api/translate` (the LLM),
then 429 with `Retry-After`; `/api/progress`, polled each second, is not counted. The client is the
address Caddy sets in `X-Forwarded-For` (a forged one is overwritten). `ALLOWED_IPS` unset: only
localhost is exempt, so `uv run wikicross` locally is never limited. Use public IPv4 addresses: a
client reaching the VM over IPv6 shows up as Docker's private gateway address, hence the A record
only. The counters live in the server process and reset when it restarts.

The extension still points at `http://127.0.0.1:8000`: for the deployment, change `BACKEND` in
`extension/background.js` and `host_permissions` in `extension/manifest.json` to `https://DOMAIN`.

### Chrome extension

`extension/` shows the same findings, with the web app's features, on every Wikipedia
(`*.wikipedia.org`, article pages): a "WikiCross · N" button opens a panel listing what this edition
states differently from the others, each finding with its AI title and description, the quotes in
English in coloured boxes (translate button: the original), "Show all", the language and dialect
filters and the irrelevant list (no "Show paragraphs": the page itself is the context). This edition's quote comes first; the AI is
asked as cards scroll into view. Its logo and name open the topic in the web app, in a new tab.
**"Show on page" (or clicking the card) shows the
evidence on the page**: in the article view and VisualEditor just that sentence is highlighted and
scrolled to; in the source editor it is selected in the wikitext, link markup and `<ref>`s included.

1. Start the backend (above) on `http://127.0.0.1:8000`.
2. `chrome://extensions` → Developer mode → **Load unpacked** → select `wikicross/extension`.
3. Open an article, e.g. `https://fi.wikipedia.org/wiki/Talvisota`, and click the button; or its
   edit view, where it loads at once.

In the article view the extension asks the backend only when the button is clicked, so reading
Wikipedia does not fetch and embed every topic visited; a page whose topic has no other edition loses
its button. Findings cover all Wikipedia versions of the article, those involving the page's own
edition first (`/api/diff?focus=fi`); a card shows three editions, the rest on "Show all".
It calls the backend from its service worker (host permission, no CORS change needed); for another
backend address, change `BACKEND` in `extension/background.js` and `host_permissions` in
`extension/manifest.json`. Findings come from when the editions were fetched, not the live page: a
paragraph edited since may still be found (by its words), or not. A topic not embedded yet takes minutes
the first time; past about five minutes Chrome may stop the service worker, and asking again shows
the result once the backend has finished. After changing `background.js`, reload the extension in
`chrome://extensions`: Chrome keeps running the old worker otherwise.

The web app and the extension must stay in sync: see [AGENTS.md](AGENTS.md).

### LLM

`LLM_PRESET` picks one of the presets in `src/wikicross/llm.py`; `LLM_API`, `LLM_URL`, `LLM_MODEL`
override single fields of it. Each preset reads its own key variable, falling back to `AI_API_KEY`,
so keys for several providers can sit in `.env` together.

| `LLM_PRESET` | API | Model | Key | Measured |
|---|---|---|---|---|
| `verda` (default) | OpenAI-compatible (`inference.verda.com`) | `kimi-k3-1-pro` | `VERDA_API_KEY` | one summary in 23 s, one translation in 4 s |
| `gemini` | Gemini `generateContent` | `gemini-4-hydrogen`, thinking `low` | `GEMINI_API_KEY` | free tier: 5 requests/min, 20/day; frequent 503 "high demand" |
| `minimax` | OpenAI-compatible (OpenRouter) | `minimax/minimax-m3.1-flash` (paid; `:free` retired) | `OPENROUTER_API_KEY` | 10 summaries in 15 s |
| `openrouter` | OpenAI-compatible | `nvidia/nemotron-3.5-super-vl:free` | `OPENROUTER_API_KEY` | free: 50 requests/day |

```bash
LLM_PRESET=minimax uv run --env-file .env wikicross
LLM_PRESET=openrouter LLM_MODEL=nvidia/nemotron-3.5-super-vl uv run --env-file .env wikicross
```

A new provider with one of these APIs is a new preset; a new API is a `(request, text)` pair in
`APIS`. Answers are cached per preset in the `llm_cache` table.

## How

No LLM is needed: articles, passages and sentences are matched across languages with bge-m3
vectors in MariaDB (HNSW for passages, an exact join for sentences), matched sentences are grouped
into one group per fact, and each group is checked for the same thing described differently, by
position on three axes: praised ↔ condemned (evaluation), fact ↔ disputed (certainty), and loaded,
emotive ↔ neutral, matter-of-fact wording (wording). The web app then asks an LLM about each finding
for a factual disagreement or a clear difference in tone or framing; findings it confirms as neither are collapsed.

Full explanation with diagrams, measured costs, tradeoffs and notes on scaling to more languages and
all of Wikipedia: [docs/how-it-works.md](docs/how-it-works.md).

**AI** (on by default, in the web app and the extension; detection never uses it): one `/api/explain`
call per finding gives its title (who says what: a factual disagreement or a different framing,
naming the editions), a description quoting the words that differ,
and each shown quote in English with those words highlighted; the original keeps the same
words highlighted. Quotes show in English: each quote's translate button shows the original on hover
(or keyboard focus) and swaps to it on click. Quotes past the first three ("Show all") and paragraphs
are translated with `/api/translate` when shown. Findings the AI does not confirm move under a "Show N
findings the AI marked as irrelevant" button, each saying why. If the LLM fails, a card has no title
and shows the quotes in their original language. Cached in `llm_cache`. The web app shows the total
number of differences, ten per page, and filters the compared editions: a language picker
(`&langs=`) and "Hide dialects" (`&dialects=0`), both kept in the URL. Filtering does not recompute:
a topic is compared once over every edition (cached), and a filter trims that result (`narrow()`:
each finding keeps the chosen editions' sentences, its deviations redone from the stored ones).

API: `GET /api/titles?q=Talvi` (titles in ≥2 languages, then English Wikipedia's suggestions),
`GET /api/diff?title=Talvisota&limit=10&offset=0` (`differences`, best first, one page of them, and
their `total`; each finding has every edition's `deviations` on its axis, shown under the "i" next
to its label; `&focus=fi` puts the findings involving that edition first; `&langs=fi,sv,ru` keeps
only those editions; `&dialects=false` leaves
out editions without a two-letter ISO 639-1 code, i.e. regional languages and varieties such as
Bavarian `bar`, Võro `vro`, Asturian `ast`, Simple English `simple`, Belarusian Taraškievica
`be-tarask`; `languages` lists every edition of the topic, filtered or not),
`GET /api/progress?title=Talvisota` (stage of a running diff),
`GET /api/context?lang=fi&page_id=…&seq=…&n=…&direction=up&count=3` (sentences around a quote),
`POST /api/explain {"passages": [{"lang", "heading", "text", "sentence"}, …]}` (one finding:
`discrepancy`, `title`, `description` and `quotes` per language: `english`, `heading`, `phrases`),
`POST /api/translate {"texts": {"fi": "…", "fi-heading": "…"}, "target": "en"}`.
