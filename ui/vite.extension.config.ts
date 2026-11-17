// The extension's scripts, each one classic script (content scripts cannot be modules) in extension/dist:
// ui/extension/content.ts → content.js, with Vue and Codex inside and its CSS for the shadow root; then,
// with `--mode background`, ui/extension/background.ts → background.js (the service worker). Rollup
// builds one classic script per run.
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const at = (path: string) => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig(({ mode }) => {
  const entry = mode === "background" ? "background" : "content";
  return {
    plugins: [vue()],
    define: { "process.env.NODE_ENV": JSON.stringify("production") },
    build: {
      outDir: at("../extension/dist"),
      emptyOutDir: entry === "content",
      copyPublicDir: false,
      lib: {
        entry: at(`./extension/${entry}.ts`),
        formats: ["iife"],
        name: `WikiCross_${entry}`,
        fileName: () => `${entry}.js`,
      },
    },
  };
});
