# WikiCross

Where do the Wikipedia editions of an article frame things differently? WikiCross fetches every
Latin- and Cyrillic-script edition of a topic live, embeds passages and sentences with bge-m3, and
compares them in MariaDB Vector. An LLM then titles and explains each finding.

Built at Junction 2026 for the [MariaDB challenge "Wikipedia through time"](https://junction2026.com/challenges/mariadb-wikipedia-through-time),
starting from MariaDB's [wikipedia-datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets),
[vector-wikipedia-rag](https://github.com/MariaDB/mariadb-vector-wikipedia-rag) and
[system-versioning-wikipedia](https://github.com/MariaDB/mariadb-system-versioning-wikipedia).
How it works, with diagrams, costs and tradeoffs: [docs/how-it-works.md](docs/how-it-works.md).

## Run

Needs Docker, uv, Node 20+ and a [Modal](https://modal.com) account (`uv run modal setup`).

```bash
docker compose up -d --wait                       # MariaDB on 127.0.0.1:3308
uv run modal deploy src/wikicross/embed_gpu.py    # bge-m3 on an H100, scales to zero when idle
make web                                          # build the web app
cp .env.example .env                              # fill in the keys
uv run --env-file .env wikicross                  # http://127.0.0.1:8000
```

To use an embedder deployed in another Modal workspace (the team's: `fabio-missagia`), skip the deploy
and run `uv run modal token new --profile fabio-missagia`, or set `MODAL_PROFILE`.

## Configuration

Every setting is an environment variable, typed and validated at start in
`src/wikicross/config.py`; [.env.example](.env.example) lists them all.

- **LLM** (required): `LLM_API_TYPE` (`openai` for any OpenAI-compatible server, or `gemini`),
  `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY`; optional `LLM_EXTRA`, JSON merged into each request.
- **Azure AI Translator**: `AZURE_TRANSLATOR_KEY`, and `AZURE_TRANSLATOR_REGION` for a regional
  resource. It translates quotes past a card's first three and paragraphs; languages Azure lacks
  (Frisian, Esperanto, …) fall back to the LLM and are logged.
- **Database**: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (defaults match compose).
- **Rate limit**: `RATE_LIMIT=1` turns it on; `ALLOWED_IPS` are exempt.

LLMs tried:

| `LLM_API_TYPE` | `LLM_URL` | `LLM_MODEL` | `LLM_EXTRA` | Notes |
|---|---|---|---|---|
| `openai` | `https://inference.verda.com/v1` | `kimi-k3-1-pro` | | ~23 s per explanation |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta` | `gemini-4-hydrogen` | `{"thinkingConfig": {"thinkingLevel": "low"}}` | free tier: 20 requests/day |
| `openai` | `https://openrouter.ai/api/v1` | `minimax/minimax-m3.1-flash` | | paid; fast |
| `openai` | `https://openrouter.ai/api/v1` | `nvidia/nemotron-3.5-super-vl:free` | `{"reasoning": {"enabled": false}}` | free: 50 requests/day |

Everything computed is cached in MariaDB (editions, vectors, differences, LLM and translator
answers), so a reload repeats no work. A topic's cached differences are recomputed when the
comparison code or model changes; to force it, delete the topic's `diff_cache` row.

## Development

| Command | |
|---|---|
| `make web` | build the web app into `src/wikicross/web/` |
| `make dev` | web app with hot reload on :5173, `/api` proxied to :8000 |
| `make extension` / `make extension-zip` | build the extension into `extension/dist/` / pack it |
| `prek install` | run the checks below on every commit (once per clone; [prek](https://github.com/j178/prek), or `uvx prek install`) |
| `make check` | the pre-commit hooks on all files (format, lint, types: Python, TypeScript/Vue, Markdown, TOML, Dockerfile, Caddyfile; fixing what they can) and pytest: must pass |
| `make profile TITLE=Joensuu EDITION=fi [NAME=…] [PROFILE_ARGS=--fresh]` | VizTracer profile of a topic's first load, into `profiles/NAME.json` |
| `make profile-view NAME=…` | open a profile (without NAME: list them) |

The front end (`ui/`) is Vue 3, TypeScript and [Codex](https://doc.wikimedia.org/codex/), shared by
the web app (`ui/web/`) and the extension (`ui/extension/`); see [AGENTS.md](AGENTS.md). Builds are
not committed. `--fresh` profiles a loaded topic as new, LLM calls included.

### CI and releases

GitHub Actions (`.github/workflows/`): `ci.yaml` runs the prek hooks, the tests and the image build on
every pull request and push to `main`, pushing `ghcr.io/ardubev16/wikicross:main` from `main`.
[release-please](https://github.com/googleapis/release-please) keeps a release PR open from the
[Conventional Commits](https://www.conventionalcommits.org/) on `main` (version in `pyproject.toml` and
`uv.lock`, `CHANGELOG.md`); merging it tags `vX.Y.Z`, publishes the GitHub release and pushes the image
as `X.Y.Z`, `X.Y` and `latest`.
[Renovate](https://docs.renovatebot.com/) keeps dependencies, actions and hooks up to date with the shared
config in [ardubev16/common](https://github.com/ardubev16/common) (`renovate.json`).

## Chrome extension

Shows the findings on any Wikipedia article, this edition's first; "Show on page" highlights the
quote in the article, or selects it in the source editor.

1. Start the backend on `http://127.0.0.1:8000`, then `make extension`.
2. `chrome://extensions` → Developer mode → **Load unpacked** → `extension/`.
3. Open an article (e.g. `https://fi.wikipedia.org/wiki/Talvisota`) and click "WikiCross".

In article view it asks the backend only on click. After changing `background.ts`, reload the
extension in `chrome://extensions`. Another backend: change `BACKEND` in `ui/extension/background.ts`
and `host_permissions` in `extension/manifest.json`.

## Deployment

The `deploy` compose profile runs the app behind Caddy, which gets and renews a Let's Encrypt
certificate. Point the domain's A record at the VM (no AAAA: over IPv6 clients appear as Docker's
gateway, breaking the rate limit), open ports 80 and 443, then:

```bash
cat >> .env <<'EOF'
COMPOSE_PROFILES=deploy
DOMAIN=wikicross.example.com
MODAL_TOKEN_ID=ak-…
MODAL_TOKEN_SECRET=as-…
EOF
docker compose up -d --build --wait
```

To bring the computed topics along: `docker compose exec mariadb mariadb-dump -uwikicross -pwikicross
wikicross | gzip > wikicross.sql.gz`, then load it with `gunzip -c … | docker compose exec -T mariadb
mariadb -uwikicross -pwikicross wikicross`.

**Rate limit** (`RATE_LIMIT=1`): outside `ALLOWED_IPS`, 60 API requests a minute and 30 AI requests
(`/api/explain`, `/api/translate`) per address; the home page states the limits. In-process counters.

**Telemetry**: the image runs under `opentelemetry-instrument`, off unless `OTEL_SDK_DISABLED=false`.
It traces requests, HTTP calls and SQL, with a span per loading step and metrics for step durations,
cache hits and translations by engine. The `otel` profile adds Grafana's `otel-lgtm` on the VM's
localhost: `COMPOSE_PROFILES=deploy,otel`, then `ssh -L 3000:127.0.0.1:3000 vm`. For another backend,
set `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`.

## API

| Endpoint | |
|---|---|
| `GET /api/titles?q=Talvi` | topic suggestions for the search box |
| `GET /api/diff?title=…&lang=fi&limit=10&offset=0` | a page of findings (`limit` ≤ 30), best first; `focus`, `langs=fi,sv`, `dialects=false` filter; `ai=false` leaves them unexplained |
| `GET /api/progress?title=…` | the steps of a running `/api/diff`, with server timings |
| `GET /api/context?lang=…&page_id=…&seq=…&n=…&direction=up` | sentences around a quote |
| `POST /api/explain {"quotes": [{lang, page_id, seq, n}, …]}` | explain one card's 2–3 quotes |
| `POST /api/translate {"quotes": […], "paragraphs": false}` | quotes (or their paragraphs) in English |
| `GET /api/limits` | the rate limits, or null when off |

The AI endpoints take quotes by their place in the database, never text from the client.

## License

Copyright (C) 2026 Lorenzo Bevilacqua. GPL-3.0-or-later; see [LICENSE](LICENSE). The front end
bundles Codex (GPL-2.0-or-later), Vue and Codex's icons (MIT).
