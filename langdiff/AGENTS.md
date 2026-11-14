# Agents

- **Keep the web app and the Chrome extension in sync.** `src/langdiff/index.html` and
  `extension/content.js` show the same findings from the same API: a change to what a finding shows
  or how you interact with it (labels, highlighting, expanding quotes, outliers) goes into both, in
  the same commit. Shared pieces carry a `Keep in sync with …` comment; only page-specific actions
  differ (AI summaries in the web app; "Show on page" / "Find in source" in the extension).
- No LLM in detection; the LLM features stay optional and off by default.
- Never read `.env` values; refer to key names only.
- Use uv (`uv run pytest`); MariaDB runs from `docker-compose.yml`.
