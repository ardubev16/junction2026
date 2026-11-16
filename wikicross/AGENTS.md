# Agents

- **Keep the web app and the Chrome extension in sync.** `src/wikicross/index.html` and
  `extension/content.js` show the same findings from the same API: a change to what a finding shows
  (labels, highlighting, outliers, ordering) goes
  into both, in the same commit. Only page-specific parts differ: the web app has the AI (titles,
  descriptions, English quotes with a per-quote original), pagination, the language and dialect
  filters, and "Show paragraphs" with expanding context; the extension has its own title template,
  "Show on page" / "Find in source" and a link to the topic in the web app.
- No LLM in detection. In the web app the AI is on by default; a failed LLM call must leave the
  findings usable (original quotes, no title).
- Never read `.env` values; refer to key names only.
- Use uv (`uv run pytest`); MariaDB runs from `docker-compose.yml`.
