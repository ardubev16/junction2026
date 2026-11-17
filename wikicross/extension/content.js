// WikiCross on Wikipedia: where the other language editions frame the same thing differently. In the
// article view and the edit views. All page text goes in through textContent, never innerHTML. Keep in
// sync with src/wikicross/index.html (see AGENTS.md).
(async () => {
  const DISPLAY = new Intl.DisplayNames(["en"], { type: "language" });
  const langName = (code) => { try { return DISPLAY.of(code); } catch { return code; } };
  const SHOWN = 3;  // editions per card before "Show all", as in the web app
  const lang = location.hostname.split(".")[0];
  const params = new URLSearchParams(location.search);
  const action = params.get("action") || "view";
  const editing = /^(edit|submit)$/.test(action) || /^(edit|editsource)$/.test(params.get("veaction") || "");
  // Articles only (MediaWiki's ns-0 body class, in every skin): not talk or special pages, not the www portal.
  if (!document.body.classList.contains("ns-0") || !(editing || action === "view")) return;
  const title = (params.get("title") || decodeURIComponent(location.pathname.replace(/^\/wiki\//, ""))).replace(/_/g, " ");

  // The Wikimedia design system, Codex, as in the web app: its tokens, CSS-only components and icons,
  // from extension/vendor (copied from npm by `npm run vendor`; see package.json).
  const vendor = (file) => fetch(chrome.runtime.getURL(`vendor/${file}`));
  const [tokens, codexStyle, CDX_ICONS] = await Promise.all([vendor("codex-design-tokens.css").then((r) => r.text()),
    vendor("codex.style.css").then((r) => r.text()), vendor("codex-icons.json").then((r) => r.json())]);
  // Codex icons, as Codex's own Icon component draws them. Keep in sync with src/wikicross/index.html.
  // innerHTML only ever sees the icon package's constant paths.
  const ICONS = { alert: "cdxIconAlert", close: "cdxIconClose", find: "cdxIconSearch", link: "cdxIconLinkExternal", list: "cdxIconListBullet",
                  info: "cdxIconInfo", chevron: "cdxIconExpand", up: "cdxIconCollapse", translate: "cdxIconLanguage", eye: "cdxIconEye",
                  eyeClosed: "cdxIconEyeClosed" };
  const icon = (name, size = "small") => {
    const i = CDX_ICONS[ICONS[name]], paths = typeof i === "string" ? i : i.ltr ?? i.default;
    const t = document.createElement("template");
    t.innerHTML = `<span class="cdx-icon cdx-icon--${size}"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><g>${paths}</g></svg></span>`;
    return t.content.firstChild;
  };
  // Same logo as the web app's header (src/wikicross/index.html).
  const logo = () => {
    const t = document.createElement("template");
    t.innerHTML = '<svg class="logo" viewBox="0 0 24 24" fill="none" stroke="#36c" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<path d="M19 11.5A8 8 0 1 0 11.5 19"/><path d="M4.6 7.2A8 8 0 0 1 18.6 8.6l-2.2.5-1.3-1.5-1.7 1.4-1.3-1.1-1.6 2.1.8 1.8-1.7 1.5-2-.8-1.3 2.4-2.2-1.1z" fill="#36c" stroke="none"/>'
      + '<circle cx="15.8" cy="15.8" r="3.3"/><path d="m18.3 18.3 2.9 2.9"/></svg>';
    return t.content.firstChild;
  };
  const $ = (tag, attrs = {}, ...kids) => {
    const el = Object.assign(document.createElement(tag), attrs);
    el.append(...kids);
    return el;
  };
  // Codex CSS-only components, as in src/wikicross/index.html (keep in sync). A button: `kind` adds
  // modifiers, e.g. "small", "quiet", "primary" (progressive).
  const BUTTON = { small: "cdx-button--size-small", quiet: "cdx-button--weight-quiet", primary: "cdx-button--action-progressive cdx-button--weight-primary",
                   progressive: "cdx-button--action-progressive", iconOnly: "cdx-button--icon-only" };
  const button = (kind, attrs, ...kids) => $("button", { type: "button", className: ["cdx-button", ...kind.split(" ").filter(Boolean).map((k) => BUTTON[k])].join(" "), ...attrs }, ...kids);
  const spinner = (label = "Loading") => $("span", { className: "cdx-progress-indicator" },
    $("span", { className: "cdx-progress-indicator__indicator" }, $("progress", { className: "cdx-progress-indicator__indicator__progress", ariaLabel: label })));
  // type: notice, warning, error, success; inline: the compact variant, for messages inside a card.
  const message = (type, text, inline) => $("div", { className: `cdx-message cdx-message--${type}${inline ? " cdx-message--inline" : ""}`, role: type === "error" ? "alert" : "status" },
    $("span", { className: "cdx-message__icon" }), $("div", { className: "cdx-message__content", textContent: text }));
  let checkboxes = 0;
  const checkbox = (input, text) => {
    Object.assign(input, { type: "checkbox", className: "cdx-checkbox__input", id: `checkbox-${++checkboxes}` });
    return $("span", { className: "cdx-checkbox" }, $("span", { className: "cdx-checkbox__wrapper" }, input, $("span", { className: "cdx-checkbox__icon" }),
      $("span", { className: "cdx-checkbox__label cdx-label" },
        $("label", { htmlFor: input.id, className: "cdx-label__label" }, $("span", { className: "cdx-label__label__text", textContent: text })))));
  };
  // A menu: a <details> whose summary is a quiet Codex button with an expand icon.
  const menu = (label, className, ...kids) => $("details", { className: `editions ${className}` },
    $("summary", { className: "cdx-button cdx-button--fake-button cdx-button--fake-button--enabled cdx-button--weight-quiet cdx-button--action-progressive cdx-button--size-small" },
      label, icon("chevron")),
    $("div", { className: "langs" }, ...kids));
  // The backend, through background.js: {data} or {error, status}.
  const ask = (message) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (reply) => {
      if (chrome.runtime.lastError || !reply) reject(Object.assign(new Error(chrome.runtime.lastError?.message || "No answer from the extension."), { status: 0 }));
      else if (reply.error) reject(Object.assign(new Error(reply.error), { status: reply.status }));
      else resolve(reply.data);
    });
  });
  const get = (path, query) => ask({ type: "get", path, params: query });
  const post = (path, body) => ask({ type: "post", path, body });
  // Text with every highlighted phrase wrapped in <mark>…</mark>, as a string (sent to the translator).
  const withMarks = (text, phrases = []) =>
    [...new Set(phrases)].reduce((t, p) => t.split(p).join(`<mark>${p}</mark>`), text);
  // That string as DOM nodes; never innerHTML, so article text cannot inject markup.
  const marked = (s) => {
    let inMark = false;
    return s.split(/(<\/?mark>)/).flatMap((piece) => {
      if (piece === "<mark>" || piece === "</mark>") { inMark = piece === "<mark>"; return []; }
      return piece ? [inMark ? $("mark", { textContent: piece }) : piece] : [];
    });
  };

  const host = document.createElement("div");
  host.id = "wikicross-host";
  const root = host.attachShadow({ mode: "open" });
  // Codex's tokens are for :root; in the shadow root they go on its host.
  root.append($("style", { textContent: tokens.replaceAll(":root", ":host") }), $("style", { textContent: codexStyle }), $("style", { textContent: `
    /* Only what Codex has no component for; colours, fonts, borders and shadows are Codex tokens. */
    :host { all: initial; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }  /* Codex components set display, which would show hidden ones */
    .toggle { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000; box-shadow: var(--box-shadow-drop-medium); font-family: var(--font-family-system-sans); }
    .panel { position: fixed; right: 16px; bottom: 64px; z-index: 2147483000; width: min(460px, calc(100vw - 32px)); max-height: 75vh; overflow: auto;
             background: var(--background-color-base); color: var(--color-base); border: 1px solid var(--border-color-base); border-radius: var(--border-radius-base);
             box-shadow: var(--box-shadow-drop-large); font: var(--font-size-small)/1.5 var(--font-family-system-sans); }
    .panel[hidden] { display: none; }
    header { position: sticky; top: 0; z-index: 1; background: var(--background-color-neutral-subtle); border-bottom: 1px solid var(--border-color-subtle);
             padding: .3rem .4rem .3rem .8rem; display: flex; justify-content: space-between; align-items: center; }
    header h2 { margin: 0; font: bold var(--font-size-medium)/1.3 var(--font-family-system-sans); }
    .home { all: unset; display: inline-flex; gap: .4rem; align-items: center; cursor: pointer; }
    .home:hover { color: var(--color-progressive); } .home:focus-visible { outline: 2px solid var(--outline-color-progressive--focus, #36c); outline-offset: 2px; }
    .logo { width: 20px; height: 20px; flex: none; }
    .body { padding: .4rem .8rem .8rem; }
    .card { border: 1px solid var(--border-color-subtle); border-radius: var(--border-radius-base); padding: .6rem .7rem; margin: .5rem 0; }
    .card.locatable { cursor: pointer; } .card.locatable:hover { border-color: var(--border-color-progressive); }
    .label { color: var(--color-warning); font-weight: bold; font-size: var(--font-size-x-small); display: inline-flex; gap: .1rem; align-items: center; margin-left: auto; }
    .label .cdx-icon { color: inherit; }
    /* The "i" next to a finding's label opens the numbers in a Codex popover (native popover, anchor
       positioned: it moves with the icon and flips if there is no room). */
    .numbers[popover] { position: absolute; inset: auto; margin: .4rem 0 0; position-area: bottom span-right;
                        position-try-fallbacks: flip-block, flip-inline; max-width: 380px; font-weight: normal; }
    .numbers[popover]:not(:popover-open) { display: none; }
    .numbers .cdx-popover__body { font-size: var(--font-size-x-small); color: var(--color-base); }
    .numbers p { margin: .3rem 0; }
    .numbers table { border-collapse: collapse; } .numbers td { padding: 0 1rem 0 0; }
    .numbers td.num { text-align: right; font-variant-numeric: tabular-nums; } .numbers tr.this td { font-weight: bold; }
    /* Keep in sync with the card styles in src/wikicross/index.html. */
    .meta { display: flex; justify-content: space-between; gap: .5rem; align-items: center; flex-wrap: wrap; font-size: var(--font-size-x-small); position: relative; }
    .card h3 { margin: .35rem 0 .2rem; font: normal var(--font-size-large)/1.35 var(--font-family-heading-main); }
    .card h3.pending { display: flex; gap: .4rem; align-items: center; font: italic var(--font-size-small) var(--font-family-system-sans); color: var(--color-subtle); }
    .summary { font: var(--font-size-small)/1.55 var(--font-family-serif); margin: 0 0 .5rem; } .summary:empty { display: none; }
    .verdict { margin: 0 0 .4rem; } .verdict:empty { display: none; } .reason { color: var(--color-subtle); font-style: italic; }
    .pending { color: var(--color-subtle); font-style: italic; }
    /* Each quote a box: header, text, footer. Rows from the subgrid: a finding's headers line up. */
    .quotes { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .6rem; margin-top: .5rem; }
    .quotes > .cdx-message { grid-column: 1 / -1; }
    .quote { display: grid; grid-row: span 3; grid-template-rows: subgrid; row-gap: .3rem; border: 1px solid var(--border-color-subtle);
             border-radius: var(--border-radius-base); padding: .45rem .6rem; background: var(--background-color-base); }
    .quote.here { border-color: var(--border-color-progressive); }
    .quote.outlier { background: var(--background-color-warning-subtle); border-color: var(--border-color-warning); }
    .quote.linked { outline: 2px solid var(--hl-line); outline-offset: 1px; }
    .quote h4 { margin: 0; font-size: var(--font-size-x-small); font-weight: normal; color: var(--color-subtle); display: flex; gap: .35rem; align-items: start; flex-wrap: wrap; }
    .quote h4 b { color: var(--color-base); border-bottom: 3px solid var(--hl-line); }
    .quote blockquote { margin: 0; font: var(--font-size-small)/1.5 var(--font-family-serif); white-space: pre-wrap; }
    .quote .foot { display: flex; justify-content: space-between; align-items: end; gap: .4rem; }
    .tr { position: relative; display: inline-flex; margin-left: auto; }
    .tr .tip { display: none; position: absolute; right: 0; bottom: 100%; z-index: 20; width: min(340px, 80vw); margin-bottom: .3rem;
               background: var(--background-color-base); border: 1px solid var(--border-color-base); border-radius: var(--border-radius-base);
               box-shadow: var(--box-shadow-drop-medium); padding: .5rem .7rem; font: var(--font-size-small)/1.5 var(--font-family-serif);
               white-space: pre-wrap; color: var(--color-base); }
    .tr:hover .tip, .tr:focus-within .tip { display: block; }
    .section { color: var(--color-subtle); font: bold 11px var(--font-family-system-sans); }
    .tools { display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .5rem; }
    /* One colour per quote of a finding (Codex option colours): its language name, its highlights, and the
       description's quotes of it. */
    .c0 { --hl: var(--background-color-option-blue); --hl-line: var(--border-color-option-blue); }
    .c1 { --hl: var(--background-color-option-green); --hl-line: var(--border-color-option-green); }
    .c2 { --hl: var(--background-color-option-purple); --hl-line: var(--border-color-option-purple); }
    .c3 { --hl: var(--background-color-option-red); --hl-line: var(--border-color-option-red); }
    mark { color: inherit; background: var(--hl, var(--background-color-option-yellow)); border-bottom: 2px solid var(--hl-line, var(--border-color-option-yellow)); padding: 0 1px; }
    /* Menus: a card's "+N more" and the language picker; their panel a Codex menu surface. */
    .editions > summary { list-style: none; } .editions > summary::-webkit-details-marker { display: none; }
    .editions[open] > summary .cdx-icon { transform: rotate(180deg); }
    .editions .langs { position: absolute; left: 0; top: 100%; z-index: 10; width: 100%; max-height: 50vh; overflow: auto; columns: 10em;
                       background: var(--background-color-base); border: 1px solid var(--border-color-base); border-radius: var(--border-radius-base);
                       padding: .5rem .7rem; box-shadow: var(--box-shadow-drop-medium); }
    .editions .langs a, .picker .cdx-checkbox { break-inside: avoid; }
    .picker .actions { column-span: all; display: flex; gap: .4rem; margin-bottom: .5rem; }
    .filters { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; margin: .2rem 0 .4rem; position: relative; }
    .irrelevant { border-top: 1px dashed var(--border-color-base); margin-top: .6rem; }
    .body > .cdx-message, .body > .cdx-button { margin: .5rem 0; }
    a { color: var(--color-link); text-decoration: none; display: inline-flex; gap: .2rem; align-items: center; } a:hover { text-decoration: underline; }
    a .cdx-icon { color: inherit; }
    .muted { color: var(--color-subtle); }
    .elsewhere { margin-top: .8rem; }
    .elsewhere > summary { padding: .5rem .2rem; } .elsewhere > .cdx-accordion__content { padding: 0; }
    .loading { display: flex; gap: .7rem; align-items: center; }
  ` }));
  const toggle = button("", { className: "cdx-button toggle" }, "WikiCross");
  const panel = $("section", { className: "panel", hidden: true });
  root.append(toggle, panel);
  document.body.append(host);
  // The page highlight: a CSS Custom Highlight over the evidence, so the page's DOM (and VisualEditor's
  // model of it) is never touched.
  document.head.append($("style", { textContent: "::highlight(wikicross) { background-color: #fef6e7; text-decoration: underline 2px #edab00; }" }));

  const textarea = document.getElementById("wpTextbox1");
  const words = (text) => [...new Set(text.toLowerCase().match(/[\p{L}\d]{4,}/gu) || [])];
  const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Where a sentence from the backend (plain text) lies in `text` (wikitext, or a paragraph's text):
  // [start, end] from its first two words to its last two, each pair allowed markup between them
  // ([[links|…]], <ref>s, footnote marks); the start nearest `near` wins. null if not found.
  function sentenceSpan(text, sentence, near) {
    const t = sentence.match(/[\p{L}\p{N}]{3,}/gu) || [];
    if (t.length < 2) return null;
    const pair = (a, b) => new RegExp(`${escape(a)}[\\s\\S]{0,60}?${escape(b)}`, "giu");
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
  function findInSource(sentence) {
    const src = textarea.value;
    const all = words(sentence);
    const anchors = [...all].sort((a, b) => b.length - a.length).slice(0, 3);
    const lower = src.toLowerCase();
    let best = null;
    for (const anchor of anchors) {
      for (let i = lower.indexOf(anchor); i !== -1; i = lower.indexOf(anchor, i + 1)) {
        const near = lower.slice(Math.max(0, i - 300), i + 300);
        const score = all.filter((w) => near.includes(w)).length;
        if (!best || score > best.score) best = { score, start: i };
      }
    }
    if (!best) return false;
    const range = sentenceSpan(src, sentence, best.start) || (() => {
      const end = src.indexOf("\n", best.start);
      return [src.lastIndexOf("\n", best.start) + 1, end === -1 ? src.length : end];
    })();
    // Put the caret there first so the browser scrolls the textarea to it, then select.
    textarea.focus();
    textarea.setSelectionRange(range[0], range[0]);
    textarea.blur();
    textarea.focus();
    textarea.setSelectionRange(...range);
    textarea.scrollIntoView({ block: "center" });
    return true;
  }

  // A Range over characters start..end of an element's text.
  function rangeAt(el, start, end) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const range = new Range();
    let pos = 0, started = false;
    for (let node; (node = walker.nextNode());) {
      const next = pos + node.data.length;
      if (!started && start < next) { range.setStart(node, start - pos); started = true; }
      if (started && end <= next) { range.setEnd(node, end - pos); return range; }
      pos = next;
    }
    return null;
  }

  // Find the paragraph (or list item, table cell) of the rendered page, in the article view or
  // VisualEditor, holding most of the evidence sentence's longer words; then highlight just the
  // sentence in it, or else the paragraph, and scroll to it.
  function findOnPage(sentence) {
    const page = document.querySelector(".ve-ce-surface") || document.getElementById("mw-content-text");
    const all = words(sentence);
    let best = null;
    for (const el of page?.querySelectorAll("p, li, dd, td, th, blockquote, figcaption") || []) {
      const text = el.textContent.toLowerCase();
      const score = all.filter((w) => text.includes(w)).length;
      // ties go to the shorter element: the cell, not the row's nested list holding it
      if (score && (!best || score > best.score || (score === best.score && text.length < best.length))) best = { el, score, length: text.length };
    }
    if (!best || best.score < Math.max(2, all.length * 0.4)) return false;
    const span = sentenceSpan(best.el.textContent, sentence, 0);
    let range = span && rangeAt(best.el, ...span);
    if (!range) { range = new Range(); range.selectNodeContents(best.el); }
    CSS.highlights.set("wikicross", new Highlight(range));
    (range.startContainer.parentElement || best.el).scrollIntoView({ block: "center", behavior: "smooth" });
    return true;
  }

  const showOnPage = (m) => (textarea && textarea.offsetParent ? findInSource(m.sentence) : findOnPage(m.sentence));

  // A quote's place on its Wikipedia page, as a text fragment the browser scrolls to and highlights. Only
  // its first and last words: the rendered page puts footnote marks ([12]) inside sentences. Keep in sync
  // with src/wikicross/index.html. The end stops at the last word's full stop, without the punctuation
  // at either end: many editions put footnote marks before the full stop ("…Энкеля»[4]."), and a mark
  // after it comes as glued text ("tilauksesta.lähde?" for "tilauksesta.[lähde?]"), neither as on the page.
  const snippetUrl = (m) => {
    const words = m.sentence.trim().replace(/[.!?]\S*$/u, "").replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "").split(/\s+/);
    const enc = (w) => encodeURIComponent(w.join(" ")).replace(/-/g, "%2D");
    const text = words.length <= 6 ? enc(words) : `${enc(words.slice(0, 3))},${enc(words.slice(-3))}`;
    return `https://${m.lang}.wikipedia.org/wiki/${encodeURIComponent(m.title.replace(/ /g, "_"))}#:~:text=${text}`;
  };

  // The numbers behind a finding, in a small window (a popover: a click outside or Escape closes it).
  // Keep in sync with src/wikicross/index.html.
  let anchors = 0;  // each "i" is the anchor its popover is placed by
  function numbers(f) {
    const sigma = (d) => { const r = Math.round(d * 10) / 10; return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(1)}σ`; };
    const rows = Object.entries(f.deviations || {}).sort((a, b) => b[1] - a[1]);
    const box = $("div", { className: "cdx-popover numbers", popover: "auto" },
      $("div", { className: "cdx-popover__header" }, $("span", { className: "cdx-popover__header__title", textContent: `How far apart: the ${f.axis} axis` })),
      $("div", { className: "cdx-popover__body" },
      $("p", { textContent: `Each sentence has a position on this axis: towards +, an edition ${f.ends[0]}; towards −, it ${f.ends[1]}. `
        + "Positions are measured against the language's own sentences, so 1σ is a typical spread within that language." }),
      $("p", { textContent: `${langName(f.lang)} sits ${sigma(f.deviations?.[f.lang] ?? f.deviation)} from the average of the others; a finding needs at least 1.2σ either way. Each edition, from its others' average:` }),
      $("table", {}, ...rows.map(([l, d]) => $("tr", { className: l === f.lang ? "this" : "" },
        $("td", { textContent: langName(l) }), $("td", { className: "num", textContent: sigma(d) })))),
      $("p", { className: "muted", textContent: `The sentences are matched as one statement: their largest cosine distance is ${f.distance.toFixed(2)} `
        + "(0 is the same meaning; up to 0.35 counts)." })));
    const anchor = `--numbers-${++anchors}`;
    box.style.positionAnchor = anchor;
    const info = button("small quiet iconOnly", { popoverTargetElement: box, title: "The numbers behind this finding",
                                                  ariaLabel: "The numbers behind this finding" }, icon("info"));
    info.style.anchorName = anchor;
    return [info, box];
  }

  // Which quote each highlighted part of the description comes from. Keep in sync with linkQuotes() in
  // src/wikicross/index.html.
  function linkQuotes(summary, members, state, quotes) {
    const norm = (s) => s.trim().toLowerCase();
    const marksOf = (p) => [...(state.english[p.lang]?.quote || "").matchAll(/<mark>(.*?)<\/mark>/gs)].map((m) => norm(m[1]))
      .concat((state.phrases[p.lang] || []).map(norm));
    const seen = {};  // a phrase in several quotes: its n-th mention goes to the n-th quote holding it
    for (const mark of summary.querySelectorAll("mark")) {
      const text = norm(mark.textContent);
      let holders = members.map((p, k) => (marksOf(p).includes(text) ? k : -1)).filter((k) => k >= 0);
      if (!holders.length) holders = members.map((p, k) => (marksOf(p).some((t) => t.includes(text) || text.includes(t)) ? k : -1)).filter((k) => k >= 0);
      if (!holders.length) continue;
      const i = holders[(seen[text] = (seen[text] ?? -1) + 1) % holders.length];
      const p = members[i], box = () => quotes.querySelector(`.quote[data-lang="${p.lang}"]`);
      mark.className = `c${i % 4}`;
      mark.title = `From the ${langName(p.lang)} quote`;
      mark.addEventListener("mouseenter", () => box()?.classList.add("linked"));
      mark.addEventListener("mouseleave", () => box()?.classList.remove("linked"));
    }
  }

  const KIND_NAMES = { factual: "Factual disagreement", bias: "Bias", framing: "Framing" };  // app.py KINDS
  // Each kind as a Codex info chip status; "none" is a finding the AI marked irrelevant.
  const KIND_STATUS = { factual: "error", bias: "warning", framing: "progressive", none: "subtle" };
  const setKind = (chip, kind, text) => {
    chip.className = `cdx-info-chip cdx-info-chip--${KIND_STATUS[kind]}`;
    chip.replaceChildren($("span", { className: "cdx-info-chip__icon" }), $("span", { className: "cdx-info-chip__text", textContent: text }));
    chip.hidden = false;
  };

  // A finding, as card() in src/wikicross/index.html (keep in sync): AI title, description and English
  // quotes, each quote in a coloured box with its translate button, and "Show all". Here this page's
  // edition comes first, with "Show on page" / "Find in source" (the page itself is the context: no
  // "Show paragraphs"), and the AI is asked only once the card is scrolled into view (`observe`): the
  // panel lists up to 30 findings.
  function finding(f, dismiss, observe) {
    const state = { english: {}, phrases: {}, original: new Set(), aiDone: false, translating: false, translateError: "",
                    all: false };
    const outliers = f.outlier ? [f.lang] : [];
    // The kind badge waits for the AI; the label only says which edition is the outlier, if one is.
    const kind = $("span", { hidden: true });
    const label = $("span", { className: "label" },
      f.outlier ? `Outlier: ${langName(f.lang)}` : "", ...numbers(f));
    // This edition first (it is the one on the page), then outliers, then the API's order.
    const rank = (m) => (m.lang === lang ? 0 : outliers.includes(m.lang) ? 1 : 2);
    const members = [...f.members].sort((a, b) => rank(a) - rank(b));
    const first = members.slice(0, SHOWN);
    const title = $("h3", { className: "pending" }, spinner("Asking the AI"), "Asking the AI how they differ…");
    const summary = $("p", { className: "summary" });
    const verdict = $("p", { className: "verdict" });
    const quotes = $("div", { className: "quotes" });
    const card = $("div", { className: "card" });
    const more = members.length > SHOWN ? button("small", {}) : null;
    const own = members.find((m) => m.lang === lang);
    const source = textarea && textarea.offsetParent;

    const translateQuotes = async (pool) => {
      const todo = pool.filter((p) => !state.english[p.lang] && (state.aiDone || !first.includes(p)));
      if (!todo.length || state.translating) return;
      state.translating = true;
      const texts = {};
      for (const p of todo) {
        texts[p.lang] = p.sentence;
        if (p.heading) texts[`${p.lang}-heading`] = p.heading;
      }
      try {
        const t = await post("/api/translate", { texts, target: "en" });
        for (const p of todo) state.english[p.lang] = { quote: t[p.lang], heading: t[`${p.lang}-heading`] ?? p.heading };
        state.translateError = "";
      } catch (err) { state.translateError = `Could not translate: ${err.message}`; }
      state.translating = false;
      renderQuotes();
    };
    const swap = (p, en, english, original) => {
      if (p.lang === "en") return "";
      if (!state.english[p.lang]) {
        const busy = !state.aiDone || state.translating;
        return busy ? $("span", { className: "pending tr", title: "Translating…" }, spinner("Translating")) : "";
      }
      const toggle = button(`small quiet iconOnly${en ? "" : " progressive"}`, { ariaPressed: String(!en),
        ariaLabel: en ? `Show the original ${langName(p.lang)} quote` : "Show the English translation" }, icon("translate"));
      toggle.dataset.lang = p.lang;
      toggle.addEventListener("click", () => {
        if (!state.original.delete(p.lang)) state.original.add(p.lang);
        renderQuotes();
        quotes.querySelector(`button[data-lang="${p.lang}"]`)?.focus();  // the re-render replaced it
      });
      return $("span", { className: "tr" }, toggle,
        $("div", { className: "tip", role: "tooltip" },
          $("div", { className: "section", textContent: en ? `Original (${langName(p.lang)})` : "English translation" }),
          ...(en ? original() : english())));
    };

    const locate = (find) => { if (!showOnPage(own)) find.replaceChildren(icon("find"), "Not found on this page"); };
    const findButton = () => {
      const find = button("small", { title: source ? "Select this in the wikitext" : "Highlight this on the page" },
        icon("find"), source ? "Find in source" : "Show on page");
      find.classList.add("find");
      find.addEventListener("click", () => locate(find));
      return find;
    };

    const renderQuotes = () => {
      const pool = state.all ? members : first;
      translateQuotes(pool);
      if (more) more.replaceChildren(icon("list"), state.all ? "Show fewer" : `Show all ${members.length} editions`, icon(state.all ? "up" : "chevron"));
      const english = (p) => state.english[p.lang] && !state.original.has(p.lang);
      quotes.replaceChildren(...pool.map((p) => {
        const en = english(p);
        const englishQuote = () => marked(state.english[p.lang].quote);
        const originalQuote = () => marked(withMarks(p.sentence, state.phrases[p.lang]));
        const quote = $("blockquote", {}, $("span", { className: "quoted" }, ...(en ? englishQuote() : originalQuote())));
        const heading = (en ? state.english[p.lang].heading : p.heading) || "(intro)";
        const i = members.indexOf(p);
        const box = $("div", { className: `quote c${i % 4}${p.lang === lang ? " here" : ""}${outliers.includes(p.lang) ? " outlier" : ""}` },
          $("h4", {}, $("b", { textContent: p.lang === lang ? `${langName(p.lang)} · this page` : langName(p.lang) }),
            $("span", { textContent: `§ ${heading}` }),
            p.lang === lang ? "" : $("a", { href: snippetUrl(p), target: "_blank", rel: "noopener", title: `Open this quote on Wikipedia: ${p.title}`,
                                            ariaLabel: `Open this quote on ${langName(p.lang)} Wikipedia` }, icon("link"))),
          quote, $("div", { className: "foot" }, p.lang === lang ? findButton() : "", swap(p, en, englishQuote, originalQuote)));
        box.dataset.lang = p.lang;
        return box;
      }), ...(state.translateError ? [message("error", state.translateError, true)] : []));
    };

    const explain = () => post("/api/explain", { passages: first.map((p) => ({ lang: p.lang, heading: p.heading || "", text: p.text, sentence: p.sentence })) })
      .then((x) => {
        title.className = "";
        title.textContent = x.title;
        if (x.discrepancy && x.kind) setKind(kind, x.kind, KIND_NAMES[x.kind]);
        if (!x.discrepancy) setKind(kind, "none", "Irrelevant");
        for (const [l, q] of Object.entries(x.quotes)) {
          state.english[l] = { quote: q.english, heading: q.heading };
          state.phrases[l] = q.phrases;
        }
        summary.replaceChildren(...marked(x.description));
        linkQuotes(summary, members, state, quotes);
        if (!x.discrepancy) {
          verdict.className = "verdict reason";
          verdict.textContent = "Marked irrelevant by the AI check: these passages neither disagree on facts nor "
            + "differ clearly in tone or framing. Their distance on the axis comes from other differences, such "
            + "as what they include, their length or detail.";
          dismiss(card);
        }
      })
      .catch((err) => {
        title.remove();
        verdict.replaceWith(message("warning", `AI unavailable, quotes in their original language: ${err.message}`, true));
      })
      .finally(() => { state.aiDone = true; renderQuotes(); });
    renderQuotes();

    const tools = $("div", { className: "tools" });
    if (more) {
      more.addEventListener("click", () => { state.all = !state.all; renderQuotes(); });
      tools.append(more);
    }

    if (own) {
      // The whole card shows this page's quote too; its links, buttons, menus and highlights keep their own action.
      card.classList.add("locatable");
      card.addEventListener("click", (e) => { if (!e.target.closest("a, button, details, mark, .tip")) locate(card.querySelector(".foot .find")); });
    }
    card.append(
      $("div", { className: "meta" }, kind, label),
      title, verdict, summary, quotes, tools);
    observe(card, explain);
    return card;
  }

  // Which editions are compared, as in the web app: a language picker and "Hide dialects". Kept for this
  // page view only (a reload starts from all editions). Keep in sync with filters() in index.html.
  let query = { langs: null, dialects: true };
  function filters(languages) {
    const sorted = [...languages].sort((a, b) => langName(a).localeCompare(langName(b)));
    const chosen = new Set(query.langs || languages);
    const boxes = sorted.map((l) => $("input", { value: l, checked: chosen.has(l) }));
    const action = (text, onClick, primary) => {
      const b = button(primary ? "small primary" : "small", { textContent: text });
      b.addEventListener("click", onClick);
      return b;
    };
    const apply = action("Apply", () => {
      const langs = boxes.filter((b) => b.checked).map((b) => b.value);
      load({ ...query, langs: langs.length === languages.length ? null : langs });
    }, true);
    const update = () => { apply.disabled = boxes.filter((b) => b.checked).length < 2; };  // a comparison needs two
    const all = (on) => { boxes.forEach((b) => { b.checked = on; }); update(); };
    boxes.forEach((b) => b.addEventListener("change", update));
    const picker = menu(query.langs ? `Languages: ${query.langs.length} of ${languages.length}` : `Languages: all ${languages.length}`, "picker",
      $("div", { className: "actions" }, action("All", () => all(true)), action("None", () => all(false)), apply),
      ...boxes.map((b) => checkbox(b, `${langName(b.value)} (${b.value})`)));
    const dialects = $("input", { checked: !query.dialects });
    dialects.addEventListener("change", () => load({ ...query, dialects: !dialects.checked }));
    return $("div", { className: "filters" }, picker, checkbox(dialects, "Hide dialects"));
  }
  // An open menu ("+N more", the language picker) closes on a click outside it, or on Escape.
  const closeMenus = (target) => { for (const d of root.querySelectorAll("details.editions[open]")) if (!target || !d.contains(target)) d.open = false; };
  root.addEventListener("click", (e) => closeMenus(e.target));
  document.addEventListener("click", (e) => { if (e.target !== host) closeMenus(null); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(null); });

  function render(data) {
    const mine = data.differences.filter((f) => f.members.some((m) => m.lang === lang));
    const elsewhere = data.differences.filter((f) => !mine.includes(f));
    const n = mine.length;
    toggle.replaceChildren(...(n ? [icon("alert")] : []), `WikiCross · ${n}`);
    toggle.className = `cdx-button toggle${n ? ` ${BUTTON.primary}` : ""}`;
    const close = button("quiet iconOnly", { title: "Close", ariaLabel: "Close" }, icon("close", "medium"));
    close.addEventListener("click", () => { panel.hidden = true; });
    const body = $("div", { className: "body" });
    // The logo and name open this topic in the web app, in a new tab (background.js knows its address).
    const home = $("button", { className: "home", type: "button", title: "Open this topic in the WikiCross web app" }, logo(), "WikiCross");
    home.addEventListener("click", () => chrome.runtime.sendMessage({ type: "open", title, lang }));
    // Findings the AI check does not confirm leave the list for a hidden one at the end, behind a button.
    const irrelevant = $("div", { className: "irrelevant", hidden: true });
    const reveal = button("small", { hidden: true, ariaExpanded: "false" });
    let dismissed = 0;
    const relabel = () => reveal.replaceChildren(icon(irrelevant.hidden ? "eye" : "eyeClosed"),
      `${irrelevant.hidden ? "Show" : "Hide"} ${dismissed} finding${dismissed === 1 ? "" : "s"} the AI marked as irrelevant`);
    reveal.addEventListener("click", () => { irrelevant.hidden = !irrelevant.hidden; reveal.ariaExpanded = String(!irrelevant.hidden); relabel(); });
    const dismiss = (card) => { dismissed++; irrelevant.append(card); reveal.hidden = false; relabel(); };
    // Each card asks the AI once it is scrolled into view in the panel.
    const seen = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { seen.unobserve(e.target); starts.get(e.target)?.(); }
    }, { root: panel });
    const starts = new WeakMap();
    const observe = (card, start) => { starts.set(card, start); seen.observe(card); };
    body.append(filters(data.languages));
    if (!data.languages.includes(lang)) {
      body.append(message("notice", `This version (${langName(lang)}) is not compared: its script is not supported yet. Below, what the others state differently.`, true));
    } else if (!data.articles.some((a) => a.lang === lang)) {
      body.append(message("notice", `This version (${langName(lang)}) is left out by the filters. Below, what the others state differently.`, true));
    } else if (!n) body.append(message("notice", "Nothing in this edition is framed differently from the other editions.", true));
    body.append(...mine.map((f) => finding(f, dismiss, observe)));
    if (elsewhere.length) {
      // A Codex accordion (CSS-only).
      body.append($("details", { className: "cdx-accordion cdx-accordion--separation-none elsewhere" },
        $("summary", {}, $("h3", { className: "cdx-accordion__header" },
          $("span", { className: "cdx-accordion__header__title", textContent: `${elsewhere.length} more between the other editions` }))),
        $("div", { className: "cdx-accordion__content" }, ...elsewhere.map((f) => finding(f, dismiss, observe)))));
    }
    body.append(reveal, irrelevant);
    panel.replaceChildren($("header", {}, $("h2", {}, home), close), body);
  }

  function showMessage(text, error) {
    const reset = button("small", { textContent: "Compare all editions" });
    reset.addEventListener("click", () => load({ langs: null, dialects: true }));
    panel.replaceChildren($("div", { className: "body" }, message(error ? "error" : "notice", text),
      query.langs || !query.dialects ? reset : ""));
  }

  let requested = false;
  function load(next = query) {
    requested = true;
    query = next;
    toggle.replaceChildren(spinner("Comparing the editions"), "WikiCross");
    // The server's current stage, polled each second while it works; only the stage is announced.
    const stage = $("span", { textContent: "Looking the topic up…" }), seconds = $("span", { className: "muted", ariaHidden: "true" });
    panel.replaceChildren($("div", { className: "body" }, $("div", { className: "loading" }, spinner("Comparing the editions"),
      $("div", {}, $("div", { role: "status" }, stage, " ", seconds),
        $("p", { className: "muted", textContent: "The first time an article is asked for, all its Wikipedia versions are fetched and embedded: this can take a few minutes." })))));
    const poll = setInterval(() => get("/api/progress", { title }).then((p) => {
      if (!p.stage) return;
      if (stage.textContent !== `${p.stage}…`) stage.textContent = `${p.stage}…`;
      seconds.textContent = `${p.seconds} s`;
    }).catch(() => {}), 1000);
    const filtered = { ...(query.langs && { langs: query.langs.join(",") }), ...(!query.dialects && { dialects: false }) };
    get("/api/diff", { title, lang, focus: lang, limit: 30, ...filtered }).then(render).catch((err) => {
      // no other edition: stay out of the way (but a filter leaving too few is the reader's to undo)
      if (!editing && err.status === 404 && !Object.keys(filtered).length) return host.remove();
      toggle.replaceChildren(err.status ? "WikiCross · –" : "WikiCross · ?");
      showMessage(err.message, true);
    }).finally(() => clearInterval(poll));
  }
  toggle.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!requested) load();
  });
  // In the edit views at once; in the article view only when asked, so that reading Wikipedia does
  // not embed every article visited.
  if (editing) load();
})();
