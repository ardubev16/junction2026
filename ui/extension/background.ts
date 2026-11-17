// Calls the WikiCross backend for the content script. Fetching here, with the host permission in
// manifest.json, avoids CORS: the page itself (https://*.wikipedia.org) could not call localhost.
// To use another backend, change BACKEND and "host_permissions" together. Built into
// extension/dist/background.js (`npm run build:extension`).
import type { Message, Reply } from "./messages";

const BACKEND = "http://127.0.0.1:8000";
const GETS = ["/api/diff", "/api/progress"];
const POSTS = ["/api/explain", "/api/translate"];

// A request that got no answer at all (the connection dropped) is sent again, twice, after 1 s and 2 s:
// AI answers are cached on the server, so asking again costs nothing once one is made. As the web app.
async function retrying(url: string, init?: RequestInit, retries = 2): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    if (!retries) throw err;
    const { promise, resolve } = Promise.withResolvers<void>();
    setTimeout(resolve, 1000 * (3 - retries));
    await promise;
    return retrying(url, init, retries - 1);
  }
}

// The backend's answer as {data} or {error, status}.
async function reply(request: Promise<Response>): Promise<Reply> {
  try {
    const r = await request;
    const body = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
    return r.ok ? { data: body } : { error: typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`, status: r.status };
  } catch {
    return { error: `WikiCross backend not reachable at ${BACKEND}: start it with  uv run wikicross`, status: 0 };
  }
}

chrome.runtime.onMessage.addListener((message: Message, _sender, sendResponse: (r: Reply) => void) => {
  if (message.type === "open") {
    chrome.tabs.create({ url: `${BACKEND}/?${new URLSearchParams({ title: message.title, lang: message.lang })}` });
    return false;
  }
  if (message.type === "get" && GETS.includes(message.path)) {
    reply(retrying(`${BACKEND}${message.path}?${new URLSearchParams(message.params)}`)).then(sendResponse);
    return true; // the answer comes asynchronously
  }
  if (message.type === "post" && POSTS.includes(message.path)) {
    reply(retrying(`${BACKEND}${message.path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(message.body) }))
      .then(sendResponse);
    return true;
  }
  return false;
});
