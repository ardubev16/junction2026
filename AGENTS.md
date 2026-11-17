# Agents

- **The web app and the Chrome extension share their UI** (`ui/shared/`, Vue): a finding shows the
  same in both (AI kind, title and description, English quotes with a per-quote original, coloured quote
  boxes, "Show all", the language and dialect filters, the irrelevant list), so change it there, once.
  Only page-specific parts differ, through `FindingCard` props: the web app (`ui/web/`) pages through
  all findings and has "Show paragraphs" with expanding context; the extension (`ui/extension/`) lists
  this edition's findings first (up to 30), asks the AI as cards scroll into view, and has "Show on
  page" / "Find in source" (the page is its context) and a link to the topic in the web app.
- **Codex for the UI** (see README, "Front end"): Codex Vue components, design tokens
  (`var(--color-…)`, never hex colours) and icons (`@wikimedia/codex-icons`). Do not hand-roll a control
  Codex has.
- **Builds are not committed**: `src/wikicross/web/` and `extension/dist/` come from `make web` /
  `make extension` (and the Dockerfile); never edit or commit them.
- No LLM in detection. The AI is on by default; a failed LLM call must leave the findings usable
  (original quotes, no title).
- Never read `.env` values; refer to key names only.
- Use uv (`uv run pytest`); MariaDB runs from `docker-compose.yml`.
