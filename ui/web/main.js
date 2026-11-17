// The web app: Vue with Codex, the Wikimedia design system (components, design tokens, icons).
import { createApp } from "vue";
import "@wikimedia/codex-design-tokens/dist/theme-wikimedia-ui.css";
import "@wikimedia/codex/dist/codex.style.css";
import "../shared/style.css";
import "./web.css";
import App from "./App.vue";

// A request that got no answer at all ("Failed to fetch": the connection dropped) is sent again, twice,
// after 1 s and 2 s: AI answers are cached on the server, so asking again costs nothing once one is made.
const request = async (url, init, retries = 2) => {
  let r;
  try {
    r = await fetch(url, init);
  } catch (err) {
    if (!retries) throw err;
    await new Promise((done) => setTimeout(done, 1000 * (3 - retries)));
    return request(url, init, retries - 1);
  }
  const data = await r.json().catch(() => ({ detail: `Server error ${r.status}` }));
  if (!r.ok) throw Object.assign(new Error(data.detail), { status: r.status });
  return data;
};
const api = {
  get: (path, params = {}) => request(`${path}?${new URLSearchParams(params)}`),
  post: (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};
createApp(App).provide("api", api).mount("#app");
