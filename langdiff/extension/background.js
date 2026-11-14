// Calls the langdiff backend for the content script. Fetching here, with the host permission in
// manifest.json, avoids CORS: the page itself (https://*.wikipedia.org) could not call localhost.
// To use another backend, change BACKEND and "host_permissions" together.
const BACKEND = "http://127.0.0.1:8000";
const PATHS = ["/api/diff", "/api/context"];

// {type: "get", path, params} -> {data} or {error, status}
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "get" || !PATHS.includes(message.path)) return false;
  fetch(`${BACKEND}${message.path}?${new URLSearchParams(message.params)}`)
    .then(async (r) => {
      const body = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
      sendResponse(r.ok ? { data: body } : { error: typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`, status: r.status });
    })
    .catch(() => sendResponse({ error: `langdiff backend not reachable at ${BACKEND}: start it with  uv run langdiff`, status: 0 }));
  return true; // the answer comes asynchronously
});
