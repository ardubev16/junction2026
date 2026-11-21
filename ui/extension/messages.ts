// What the content script asks the background (background.ts), and its answers.
// The WikiCross backend: change it with "host_permissions" in manifest.json.
export const BACKEND = "http://127.0.0.1:8000";
export type Message =
  | { type: "open"; title: string; lang: string } // the web app on that topic, in a new tab
  | { type: "get"; path: string; params: Record<string, string> }
  | { type: "post"; path: string; body: unknown };
/** The backend's answer, or its error with the HTTP status (0: no answer at all). */
export type Reply = { data: unknown } | { error: string; status: number };
