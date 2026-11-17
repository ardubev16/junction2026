// Copies the Wikimedia design system (Codex: tokens, styles, icons, Vue components) and Vue from
// node_modules into the web app (src/wikicross/static/vendor) and the extension (extension/vendor).
// The copies are committed, so running the app needs no Node; after changing a version in
// package.json: `npm install && npm run vendor`.
import { copyFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = (name, file) => join(root, "node_modules", name, "dist", file);
const files = {
  "codex-design-tokens.css": pkg("@wikimedia/codex-design-tokens", "theme-wikimedia-ui.css"),
  "codex.style.css": pkg("@wikimedia/codex", "codex.style.css"),
  "codex-icons.json": pkg("@wikimedia/codex-icons", "codex-icons.json"),
};
const targets = {
  // The web app also mounts Codex Vue components (TypeaheadSearch), so it gets Codex's ES module and Vue.
  "src/wikicross/static/vendor": { ...files, "codex.js": pkg("@wikimedia/codex", "codex.js"),
    "vue.runtime.esm-browser.prod.js": pkg("vue", "vue.runtime.esm-browser.prod.js") },
  "extension/vendor": files,
};
for (const [dir, list] of Object.entries(targets)) {
  rmSync(join(root, dir), { recursive: true, force: true });
  mkdirSync(join(root, dir), { recursive: true });
  for (const [name, from] of Object.entries(list)) copyFileSync(from, join(root, dir, name));
  console.log(`${dir}: ${Object.keys(list).join(", ")}`);
}
