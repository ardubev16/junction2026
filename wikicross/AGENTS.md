# Agents

- **Keep the web app and the Chrome extension in sync.** `src/wikicross/index.html` and
  `extension/content.js` show the same findings from the same API, with the same features: AI
  titles and descriptions, English quotes with a per-quote original, coloured quote boxes, "Show
  all", the language and dialect filters, the irrelevant list. A change to what a finding shows goes
  into both, in the same commit. Only page-specific parts differ: the web app pages through all
  findings and has "Show paragraphs" with expanding context; the extension lists this edition's
  findings first (up to 30), asks the AI as cards scroll into view, and has "Show on page" / "Find in
  source" (the page is its context) and a link to the topic in the web app.
- No LLM in detection. The AI is on by default; a failed LLM call must leave the findings usable
  (original quotes, no title).
- Never read `.env` values; refer to key names only.
- Use uv (`uv run pytest`); MariaDB runs from `docker-compose.yml`.
