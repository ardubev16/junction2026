// The extension's content script: ui/extension/content.js → extension/dist/content.js, one classic
// script with Vue and Codex inside (content scripts cannot be modules); its CSS goes into the shadow root.
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const at = (path) => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
  plugins: [vue()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: at("../extension/dist"), emptyOutDir: true, copyPublicDir: false,
    lib: { entry: at("./extension/content.js"), formats: ["iife"], name: "WikiCross", fileName: () => "content.js" },
  },
});
