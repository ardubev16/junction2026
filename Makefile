# Front-end builds: the web app (served by the server) and the Chrome extension's scripts, both from ui/
# (Vue + Codex, TypeScript: type-checked first). Their output is not committed; the Dockerfile builds the
# web app itself. Also: profiling the pipeline of a new article.
.PHONY: all web extension extension-zip dev clean profile profile-view

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

# The pipeline of a new article under VizTracer (scripts/profile.py) into profile.json, e.g.
#   make profile TITLE=Joensuu EDITION=fi
#   make profile TITLE=Talvisota EDITION=fi PROFILE_ARGS="--fresh --no-ai"
# EDITION, not LANG: make would take the shell's locale.
EDITION ?= en
profile:
	@test -n "$(TITLE)" || { echo 'usage: make profile TITLE=Joensuu [EDITION=fi] [PROFILE_ARGS="--fresh --no-ai"]'; exit 2; }
	uv run --env-file .env scripts/profile.py "$(TITLE)" --lang "$(EDITION)" $(PROFILE_ARGS)

# The timeline of the last `make profile`, in the browser
profile-view:
	uv run vizviewer profile.json
