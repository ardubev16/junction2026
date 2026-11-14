# Agents

- **Keep the web app and the Chrome extension in sync.** `src/langdiff/index.html` and
  `extension/content.js` show the same findings from the same API: a change to what a finding shows
  (labels, the red Discrepancy / amber Impartiality marks, highlighting, outliers, ordering) goes
  into both, in the same commit. Only page-specific parts differ: the web app has AI summaries and
  "Show paragraphs" with expanding context; the extension has the page edition's leaning, and "Show
  on page" / "Find in source".
- No LLM in detection; the LLM features stay optional and off by default.
- Never read `.env` values; refer to key names only.
- Use uv (`uv run pytest`); MariaDB runs from `docker-compose.yml`.
