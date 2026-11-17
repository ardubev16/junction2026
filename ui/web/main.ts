// The web app: Vue with Codex, the Wikimedia design system (components, design tokens, icons).
import { createApp } from "vue";
import "@wikimedia/codex-design-tokens/dist/theme-wikimedia-ui.css";
import "@wikimedia/codex/dist/codex.style.css";
import "../shared/style.css";
import "./web.css";
import App from "./App.vue";
import { API, type Api } from "../shared/types";
import { searchParams } from "../shared/util";

// A request that got no answer at all ("Failed to fetch": the connection dropped) is sent again, twice,
// after 1 s and 2 s: AI answers are cached on the server, so asking again costs nothing once one is made.
const request = async <T>(url: string, init?: RequestInit, retries = 2): Promise<T> => {
  let r: Response;
  try {
    r = await fetch(url, init);
  } catch (err) {
    if (!retries) throw err;
    const { promise, resolve } = Promise.withResolvers<void>();
    setTimeout(resolve, 1000 * (3 - retries));
    await promise;
    return request(url, init, retries - 1);
  }
  const data = await r.json().catch(() => ({ detail: `Server error ${r.status}` }));
  if (!r.ok) throw Object.assign(new Error(data.detail), { status: r.status });
  return data as T;
};
const api: Api = {
  get: (path, params) => request(`${path}?${searchParams(params)}`),
  post: (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};
createApp(App).provide(API, api).mount("#app");
