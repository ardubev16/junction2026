# Front-end builds: the web app (served by the server) and the Chrome extension's content script, both
# from ui/ (Vue + Codex). Their output is not committed; the Dockerfile builds the web app itself.
.PHONY: all web extension extension-zip dev clean

all: web extension

node_modules: package.json package-lock.json
	npm ci
	@touch node_modules

# src/wikicross/web: served at / by app.py (`uv run wikicross`)
web: node_modules
	npm run build:web

# extension/dist/content.js: then load extension/ unpacked in chrome://extensions
extension: node_modules
	npm run build:extension

# extension.zip: the extension, packed for the Chrome Web Store
extension-zip: extension
	rm -f extension.zip
	cd extension && zip -qr ../extension.zip manifest.json background.js dist

# The web app with hot reload on http://localhost:5173, /api passed to the backend on 127.0.0.1:8000
dev: node_modules
	npm run dev

clean:
	rm -rf src/wikicross/web extension/dist extension.zip
