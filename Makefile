# Front-end builds: the web app (served by the server) and the Chrome extension's scripts, both from ui/
# (Vue + Codex, TypeScript: type-checked first). Their output is not committed; the Dockerfile builds the
# web app itself. Also: checks (the prek hooks, pytest) and profiling the pipeline of a new article.
.PHONY: all web extension extension-zip dev clean check profile profile-view

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

# Everything a change must pass: the pre-commit hooks on every file (.pre-commit-config.yaml: format,
# lint and types for Python, TypeScript/Vue and the rest; they fix what they can), then the tests.
# prek is not a Python dependency: uvx runs it.
check: node_modules
	uvx prek run --all-files
	uv run pytest -q
