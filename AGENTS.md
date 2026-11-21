# Agents

- **The web app and the Chrome extension share their UI** (`ui/shared/`, Vue): a finding shows the
  same in both (kind, AI title and description, English quotes with a per-quote original, coloured quote
  boxes, "Show all", the kind, language and dialect filters), so change it there, once.
  Only page-specific parts differ, through `FindingCard` props: the web app (`ui/web/`) pages through
  all findings and has "Show paragraphs" with expanding context; the extension (`ui/extension/`) lists
  this edition's findings first (up to 30), asks the AI as cards scroll into view, and has "Show on
  page" / "Find in source" (the page is its context) and a link to the topic in the web app.
- **Codex for the UI** (<https://doc.wikimedia.org/codex/>): Codex Vue components, design tokens
  (`var(--color-…)`, never hex colours) and icons (`@wikimedia/codex-icons`). Do not hand-roll a control
  Codex has.
- **TypeScript for the front end** (`strict`, `tsconfig.json`): `.ts` files and `<script setup lang="ts">`;
  the backend's answers are typed in `ui/shared/types.ts`, so change them there with `app.py`. Builds
  type-check first; `npm run typecheck` alone.
- **Builds are not committed**: `src/wikicross/web/` and `extension/dist/` come from `make web` /
  `make extension` (and the Dockerfile); never edit or commit them.
- No LLM in detection. The AI is on by default; a failed LLM call must leave the findings usable
  (original quotes, no title). After changing the explain prompt, the LLM or a threshold in `compare.py`,
  run `make eval` (labelled findings in `evals/`); add a case for each wrong finding you fix.
- Never read `.env` values; refer to key names only.
- Use uv (`uv run pytest`); MariaDB runs from `docker-compose.yml`.
- **`make check` must pass**: the prek hooks (`.pre-commit-config.yaml`: format, lint and types for Python,
  TypeScript/Vue, Markdown, TOML, the Dockerfile, …) and the tests. Fix the code rather than silencing a
  rule; a new ignore (`pyproject.toml`, `eslint.config.js`, `.markdownlint-cli2.yaml`) or a `noqa` needs its
  reason beside it.
- **Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)** (`feat:`,
  `fix:`, `docs:`, `refactor:`, `build:`, …; `!` for breaking changes): release-please derives versions
  and the changelog from them.
