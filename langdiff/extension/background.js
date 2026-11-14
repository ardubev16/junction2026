// Calls the langdiff backend for the content script. Fetching here, with the host permission in
// manifest.json, avoids CORS: the page itself (https://*.wikipedia.org) could not call localhost.
// To use another backend, change BACKEND and "host_permissions" together.
const BACKEND = "http://127.0.0.1:8000";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "diff") return false;
  fetch(`${BACKEND}/api/diff?${new URLSearchParams({ title: message.title, limit: 30 })}`)
    .then(async (r) => {
      const body = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }));
      sendResponse(r.ok ? { data: body } : { error: body.detail || `HTTP ${r.status}` });
    })
    .catch(() => sendResponse({ error: `langdiff backend not reachable at ${BACKEND}: start it with  uv run langdiff` }));
  return true; // the answer comes asynchronously
});
