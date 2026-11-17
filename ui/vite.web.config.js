// The web app: ui/web → src/wikicross/web (served by app.py). `npm run dev` serves it with hot reload,
// passing /api to the backend on 127.0.0.1:8000.
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
  root: at("./web"),
  plugins: [vue()],
  build: { outDir: at("../src/wikicross/web"), emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
