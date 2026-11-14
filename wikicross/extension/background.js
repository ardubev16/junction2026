// Calls the WikiCross backend for the content script. Fetching here, with the host permission in
// manifest.json, avoids CORS: the page itself (https://*.wikipedia.org) could not call localhost.
// To use another backend, change BACKEND and "host_permissions" together.
const BACKEND = "http://127.0.0.1:8000";
const PATHS = ["/api/diff", "/api/progress"];

// {type: "open", title, lang}: the web app on that topic, in a new tab.
// {type: "get", path, params} -> {data} or {error, status}
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "open") {
    chrome.tabs.create({ url: `${BACKEND}/?${new URLSearchParams({ title: message.title, lang: message.lang })}` });
    return false;
  }
  if (message?.type !== "get" || !PATHS.includes(message.path)) return false;
  fetch(`${BACKEND}${message.path}?${new URLSearchParams(message.params)}`)
    .then(async (r) => {
      const body = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
      sendResponse(r.ok ? { data: body } : { error: typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`, status: r.status });
    })
    .catch(() => sendResponse({ error: `WikiCross backend not reachable at ${BACKEND}: start it with  uv run wikicross`, status: 0 }));
  return true; // the answer comes asynchronously
});
