# Front-end builds: the web app (served by the server) and the Chrome extension's scripts, both from ui/
# (Vue + Codex, TypeScript: type-checked first). Their output is not committed; the Dockerfile builds the
# web app itself. Also: checks (ruff, ty, vue-tsc, pytest) and profiling the pipeline of a new article.
.PHONY: all web extension extension-zip dev clean check fix profile profile-view

all: web extension

node_modules: package.json package-lock.json
	npm ci
	@touch node_modules

# src/wikicross/web: served at / by app.py (`uv run wikicross`)
web: node_modules
	npm run build:web

# extension/dist/content.js and background.js: then load extension/ unpacked in chrome://extensions
extension: node_modules
	npm run build:extension

# extension.zip: the extension, packed for the Chrome Web Store
extension-zip: extension
	rm -f extension.zip
	cd extension && zip -qr ../extension.zip manifest.json dist

# The web app with hot reload on http://localhost:5173, /api passed to the backend on 127.0.0.1:8000
dev: node_modules
	npm run dev

clean:
	rm -rf src/wikicross/web extension/dist extension.zip

# The pipeline of a new article under VizTracer (scripts/profile.py) into profiles/NAME.json (NAME: the
# title unless given), then its timeline in the browser, e.g.
#   make profile TITLE=Joensuu EDITION=fi                 # profiles/Joensuu.json
#   make profile TITLE=Trento PROFILE_ARGS=--fresh NAME=trento-fresh
#   make profile-view NAME=trento-fresh
# EDITION, not LANG: make would take the shell's locale.
EDITION ?= en
NAME ?= $(TITLE)
profile:
	@test -n "$(TITLE)" || { echo 'usage: make profile TITLE=Joensuu [EDITION=fi] [NAME=joensuu-1] [PROFILE_ARGS="--fresh --no-ai"]'; exit 2; }
	uv run --env-file .env scripts/profile.py "$(TITLE)" --lang "$(EDITION)" -o "profiles/$(NAME).json" $(PROFILE_ARGS)

profile-view:
	@test -n "$(NAME)" || { echo 'usage: make profile-view NAME=Joensuu   (profiles/: $(notdir $(wildcard profiles/*.json)))'; exit 2; }
	uv run vizviewer "profiles/$(NAME).json"

# Everything a change must pass: Python lint, format and types (ruff, ty), the front end's types
# (vue-tsc), the tests
check: node_modules
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check
	npm run typecheck
	uv run pytest -q

# What ruff can fix by itself: lint fixes, then formatting
fix:
	uv run ruff check --fix .
	uv run ruff format .
