// Helpers shared by the web app and the extension.

const DISPLAY = new Intl.DisplayNames(["en"], { type: "language" });
export const langName = (code) => { try { return DISPLAY.of(code); } catch { return code; } };

export const SHOWN = 3;  // quotes per card; the rest on "Show all"

export const KIND_NAMES = { factual: "Factual disagreement", bias: "Bias", framing: "Framing" };  // app.py KINDS
// Each kind as a Codex info chip status; "none" is a finding the AI marked irrelevant.
export const KIND_STATUS = { factual: "error", bias: "warning", framing: "progressive", none: "notice" };

// Text with every highlighted phrase wrapped in <mark>…</mark>, as a string (sent to the translator).
export const withMarks = (text, phrases = []) =>
  [...new Set(phrases)].reduce((t, p) => t.split(p).join(`<mark>${p}</mark>`), text);

// That string as parts [{ text, mark }]: rendered as text nodes, never as HTML, so article text cannot
// inject markup.
export const markParts = (s = "") => {
  let mark = false;
  return s.split(/(<\/?mark>)/).flatMap((text) => {
    if (text === "<mark>" || text === "</mark>") { mark = text === "<mark>"; return []; }
    return text ? [{ text, mark }] : [];
  });
};

// Which quote each highlighted part of the AI's description comes from (its index in `members`), so it
// takes that quote's colour and outlines the quote's box on hover. Matched by the quotes' marked words,
// exactly, then by containment; a phrase in several quotes: its n-th mention goes to the n-th quote
// holding it. Unmatched parts keep the plain highlight.
export function linkMarks(parts, members, english, phrases) {
  const norm = (s) => s.trim().toLowerCase();
  const marksOf = (p) => [...(english[p.lang]?.quote || "").matchAll(/<mark>(.*?)<\/mark>/gs)].map((m) => norm(m[1]))
    .concat((phrases[p.lang] || []).map(norm));
  const seen = {};
  return parts.map((part) => {
    if (!part.mark) return part;
    const text = norm(part.text);
    let holders = members.map((p, k) => (marksOf(p).includes(text) ? k : -1)).filter((k) => k >= 0);
    if (!holders.length) holders = members.map((p, k) => (marksOf(p).some((t) => t.includes(text) || text.includes(t)) ? k : -1)).filter((k) => k >= 0);
    if (!holders.length) return part;
    const i = holders[(seen[text] = (seen[text] ?? -1) + 1) % holders.length];
    return { ...part, quote: i, lang: members[i].lang };
  });
}

// A quote's place on its Wikipedia page, as a text fragment the browser scrolls to and highlights. Only
// its first and last words: the rendered page puts footnote marks ([12]) inside sentences. The end
// stops at the last word's full stop, without the punctuation at either end: many editions put footnote
// marks before the full stop ("…Энкеля»[4]."), and a mark after it comes as glued text
// ("tilauksesta.lähde?" for "tilauksesta.[lähde?]"), neither as on the page.
export const snippetUrl = (m) => {
  const words = m.sentence.trim().replace(/[.!?]\S*$/u, "").replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "").split(/\s+/);
  const enc = (w) => encodeURIComponent(w.join(" ")).replace(/-/g, "%2D");
  const text = words.length <= 6 ? enc(words) : `${enc(words.slice(0, 3))},${enc(words.slice(-3))}`;
  return `https://${m.lang}.wikipedia.org/wiki/${encodeURIComponent(m.title.replace(/ /g, "_"))}#:~:text=${text}`;
};

export const sigma = (d) => { const r = Math.round(d * 10) / 10; return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(1)}σ`; };
