// The web app: Vue with Codex, the Wikimedia design system (components, design tokens, icons).
import { createApp } from "vue";
import "@wikimedia/codex-design-tokens/dist/theme-wikimedia-ui.css";
import "@wikimedia/codex/dist/codex.style.css";
import "../shared/style.css";
import "./web.css";
import App from "./App.vue";

const request = async (url, init) => {
  const r = await fetch(url, init);
  const data = await r.json().catch(() => ({ detail: `Server error ${r.status}` }));
  if (!r.ok) throw Object.assign(new Error(data.detail), { status: r.status });
  return data;
};
const api = {
  get: (path, params = {}) => request(`${path}?${new URLSearchParams(params)}`),
  post: (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};
createApp(App).provide("api", api).mount("#app");
