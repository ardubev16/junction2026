// WikiCross on Wikipedia: where the other language editions frame the same thing differently. In the
// article view and the edit views. Its panel (Panel.vue) shares the finding cards with the web app; this
// part finds a finding's evidence on the page. Built into extension/dist/content.js (`npm run build`).
import { createApp } from "vue";
import tokens from "@wikimedia/codex-design-tokens/dist/theme-wikimedia-ui.css?inline";
import codex from "@wikimedia/codex/dist/codex.style.css?inline";
import shared from "../shared/style.css?inline";
import { API, type Api, type Member } from "../shared/types";
import { searchParams } from "../shared/util";
import own from "./extension.css?inline";
import type { Message, Reply } from "./messages";
import Panel from "./Panel.vue";

const lang = location.hostname.split(".")[0];
const params = new URLSearchParams(location.search);
const action = params.get("action") || "view";
const editing = /^(edit|submit)$/.test(action) || /^(edit|editsource)$/.test(params.get("veaction") || "");
// Articles only (MediaWiki's ns-0 body class, in every skin): not talk or special pages, not the www portal.
const article = document.body.classList.contains("ns-0") && (editing || action === "view");
const title = (params.get("title") || decodeURIComponent(location.pathname.replace(/^\/wiki\//, ""))).replace(/_/g, " ");

const textarea = document.getElementById("wpTextbox1") as HTMLTextAreaElement | null;
const inSource = () => !!textarea?.offsetParent;  // the source editor is open
const words = (text: string) => [...new Set(text.toLowerCase().match(/[\p{L}\d]{4,}/gu) || [])];
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// Where a sentence from the backend (plain text) lies in `text` (wikitext, or a paragraph's text):
// [start, end] from its first two words to its last two, each pair allowed markup between them
// ([[links|…]], <ref>s, footnote marks); the start nearest `near` wins. null if not found.
function sentenceSpan(text: string, sentence: string, near: number): [number, number] | null {
  const t = sentence.match(/[\p{L}\p{N}]{3,}/gu) || [];
  if (t.length < 2) return null;
  const pair = (a: string, b: string) => new RegExp(`${escape(a)}[\\s\\S]{0,60}?${escape(b)}`, "giu");
  for (let i = 0; i + 1 < Math.min(t.length, 5); i++) {  // later word pairs if the first ones were reworded
    const starts = [...text.matchAll(pair(t[i], t[i + 1]))].sort((a, b) => Math.abs(a.index - near) - Math.abs(b.index - near));
    if (!starts.length) continue;
    let start = starts[0].index;
    if (i > 0) {  // its first words are not there as written ("[[Noottikriisi]]n", a long <ref>): back to the sentence's start
      const before = text.slice(Math.max(0, start - 150), start);
      const cut = [...before.matchAll(/[.!?]\s+|\n|\/>\s*|<\/ref>\s*/g)].at(-1);
      if (cut) start -= before.length - (cut.index + cut[0].length);
    }
    const tail = text.slice(start, start + sentence.length * 2 + 200);
    for (let j = t.length - 1; j > i + 1; j--) {
      const last = pair(t[j - 1], t[j]).exec(tail);
      if (last) {
        const end = start + last.index + last[0].length;
        return [start, /[.!?]/.test(text[end] || "") ? end + 1 : end];
      }
    }
    return [start, starts[0].index + starts[0][0].length];
  }
  return null;
}

// Find the evidence sentence in the wikitext, which adds [[links]], '''bold''' and <ref>s to the
// backend's plain text: the place where most of its longer words occur together is the anchor. Then
// select the sentence there, or else the whole line.
function findInSource(box: HTMLTextAreaElement, sentence: string): boolean {
  const src = box.value;
  const all = words(sentence);
  const anchors = [...all].sort((a, b) => b.length - a.length).slice(0, 3);
  const lower = src.toLowerCase();
  let best: { score: number; start: number } | null = null;
  for (const anchor of anchors) {
    for (let i = lower.indexOf(anchor); i !== -1; i = lower.indexOf(anchor, i + 1)) {
      const near = lower.slice(Math.max(0, i - 300), i + 300);
      const score = all.filter((w) => near.includes(w)).length;
      if (!best || score > best.score) best = { score, start: i };
    }
  }
  if (!best) return false;
  const lineEnd = src.indexOf("\n", best.start);
  const range = sentenceSpan(src, sentence, best.start) ?? [src.lastIndexOf("\n", best.start) + 1, lineEnd === -1 ? src.length : lineEnd];
  // Put the caret there first so the browser scrolls the textarea to it, then select.
  box.focus();
  box.setSelectionRange(range[0], range[0]);
  box.blur();
  box.focus();
  box.setSelectionRange(...range);
  box.scrollIntoView({ block: "center" });
  return true;
}

// A Range over characters start..end of an element's text.
function rangeAt(el: Element, start: number, end: number): Range | null {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const range = new Range();
  let pos = 0, started = false;
  for (let node: Node | null; (node = walker.nextNode());) {
    const next = pos + (node as Text).data.length;
    if (!started && start < next) { range.setStart(node, start - pos); started = true; }
    if (started && end <= next) { range.setEnd(node, end - pos); return range; }
    pos = next;
  }
  return null;
}

// Find the paragraph (or list item, table cell) of the rendered page, in the article view or
// VisualEditor, holding most of the evidence sentence's longer words; then highlight just the
// sentence in it, or else the paragraph, and scroll to it.
function findOnPage(sentence: string): boolean {
  const page = document.querySelector(".ve-ce-surface") || document.getElementById("mw-content-text");
  const all = words(sentence);
  let best: { el: Element; score: number; length: number } | null = null;
  for (const el of page?.querySelectorAll("p, li, dd, td, th, blockquote, figcaption") ?? []) {
    const text = (el.textContent ?? "").toLowerCase();
    const score = all.filter((w) => text.includes(w)).length;
    // ties go to the shorter element: the cell, not the row's nested list holding it
    if (score && (!best || score > best.score || (score === best.score && text.length < best.length))) best = { el, score, length: text.length };
  }
  if (!best || best.score < Math.max(2, all.length * 0.4)) return false;
  const span = sentenceSpan(best.el.textContent ?? "", sentence, 0);
  let range = span && rangeAt(best.el, ...span);
  if (!range) { range = new Range(); range.selectNodeContents(best.el); }
  CSS.highlights.set("wikicross", new Highlight(range));
  (range.startContainer.parentElement || best.el).scrollIntoView({ block: "center", behavior: "smooth" });
  return true;
}

const showOnPage = (m: Member) => (textarea && inSource() ? findInSource(textarea, m.sentence) : findOnPage(m.sentence));

// The backend, through background.ts: its data, or an error with the HTTP status (0: no answer).
async function ask<T>(message: Message): Promise<T> {
  let reply: Reply | undefined;
  try {
    reply = await chrome.runtime.sendMessage<Message, Reply>(message);
  } catch (err) {
    throw Object.assign(err instanceof Error ? err : new Error(String(err)), { status: 0 });
  }
  if (!reply) throw Object.assign(new Error("No answer from the extension."), { status: 0 });
  if ("error" in reply) throw Object.assign(new Error(reply.error), { status: reply.status });
  return reply.data as T;
}
const api: Api = {
  get: (path, query) => ask({ type: "get", path, params: Object.fromEntries(searchParams(query)) }),
  post: (path, body) => ask({ type: "post", path, body }),
};

if (article) {
  // The panel lives in a shadow root, away from the page's styles. Codex's tokens are for :root; here
  // they go on the shadow host.
  const host = document.createElement("div");
  host.id = "wikicross-host";
  const root = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = [tokens.replaceAll(":root", ":host"), codex, shared, own].join("\n");
  const container = document.createElement("div");
  container.className = "wikicross";
  root.append(style, container);
  document.body.append(host);
  // The page highlight: a CSS Custom Highlight over the evidence, so the page's DOM (and VisualEditor's
  // model of it) is never touched.
  const highlight = document.createElement("style");
  highlight.textContent = "::highlight(wikicross) { background-color: #fef6e7; text-decoration: underline 2px #edab00; }";
  document.head.append(highlight);
  // Codex popovers close on a mousedown or focus outside them, checked on the document, where an event
  // from the shadow root looks like it came from the host: keep events inside a popover, or on the button
  // that opens one, from reaching the document.
  for (const type of ["mousedown", "focusin"]) {
    container.addEventListener(type, (e) => {
      if (e.composedPath().some((n) => n instanceof HTMLElement && (n.classList.contains("cdx-popover") || n.dataset.popoverAnchor !== undefined))) {
        e.stopPropagation();
      }
    });
  }
  createApp(Panel, {
    title, lang, editing,
    locate: showOnPage,
    locateLabel: () => (inSource() ? { text: "Find in source", title: "Select this in the wikitext" } : { text: "Show on page", title: "Highlight this on the page" }),
    openHome: () => { chrome.runtime.sendMessage<Message>({ type: "open", title, lang }); },
    remove: () => host.remove(),
  }).provide(API, api).provide("CdxTeleportTarget", container).mount(container);
}
