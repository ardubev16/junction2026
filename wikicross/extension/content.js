// WikiCross on Wikipedia: where the other language editions frame the same thing differently. In the
// article view and the edit views. All page text goes in through textContent, never innerHTML. Keep in
// sync with src/wikicross/index.html (see AGENTS.md).
(() => {
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

  // Icons as SVG: font glyphs show as empty squares where the font lacks them. Constant markup only.
  const ICONS = {
    alert: '<path d="M10 2.5 18.5 17.5h-17z"/><path d="M10 8v4M10 14.8v.2"/>',
    scale: '<path d="M10 3v14M6 17h8M3 6h14M5.5 6 3 12h5zM14.5 6 12 12h5z"/>',
    close: '<path d="m5 5 10 10M15 5 5 15"/>',
    find: '<circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4.5 4.5"/>',
    link: '<path d="M11 3h6v6M17 3l-8 8M14 12v5H3V6h5"/>',
    list: '<path d="M7 5h10M7 10h10M7 15h10M3 5h.01M3 10h.01M3 15h.01"/>',
    info: '<circle cx="10" cy="10" r="7.5"/><path d="M10 9v5M10 6.2v.1"/>',
    pair: '<path d="M2 10h16M5 7l-3 3 3 3M15 7l3 3-3 3"/>',
    chevron: '<path d="m5 8 5 5 5-5"/>',
    up: '<path d="m5 12 5-5 5 5"/>',
    paragraph: '<path d="M10 3v14M14 3v14M16 3H8.5a3.5 3.5 0 0 0 0 7H10"/>',
    translate: '<path d="M3 5h8M7 3v2M5 5c0 4 3 7 6 8M9 5c0 3-2 6-6 8M11 17l3.5-8 3.5 8M12.2 14.5h4.6"/>',
    eye: '<path d="M2 10s3-6 8-6 8 6 8 6-3 6-8 6-8-6-8-6z"/><circle cx="10" cy="10" r="2.5"/>',
  };
  const icon = (name) => {
    const t = document.createElement("template");
    t.innerHTML = `<svg class="icon" viewBox="0 0 20 20" aria-hidden="true">${ICONS[name]}</svg>`;
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
  const spinner = () => $("span", { className: "spinner", ariaHidden: "true" });
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
  root.append($("style", { textContent: `
    :host { all: initial; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }  /* button styles set display, which would show hidden buttons */
    .icon { width: 1.1em; height: 1.1em; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; vertical-align: -.2em; flex: none; }
    .toggle { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000; display: inline-flex; gap: .4rem; align-items: center;
              font: bold 14px/1 sans-serif; padding: .6rem .9rem; border-radius: 2px; border: 1px solid #36c; background: #36c; color: #fff; cursor: pointer;
              box-shadow: 0 2px 6px rgba(0,0,0,.25); }
    .toggle.quiet { background: #f8f9fa; color: #202122; border-color: #a2a9b1; }
    .panel { position: fixed; right: 16px; bottom: 64px; z-index: 2147483000; width: min(460px, calc(100vw - 32px)); max-height: 75vh; overflow: auto;
             background: #fff; color: #202122; border: 1px solid #a2a9b1; border-radius: 2px; box-shadow: 0 4px 16px rgba(0,0,0,.25);
             font: 14px/1.5 -apple-system, "Segoe UI", Roboto, Lato, "Helvetica Neue", Arial, sans-serif; }
    .panel[hidden] { display: none; }
    header { position: sticky; top: 0; background: #f8f9fa; border-bottom: 1px solid #c8ccd1; padding: .4rem .8rem; display: flex; justify-content: space-between; align-items: center; }
    header h2 { margin: 0; font: bold 15px/1.3 sans-serif; }
    .home { all: unset; display: inline-flex; gap: .4rem; align-items: center; cursor: pointer; }
    .home:hover { color: #36c; } .home:focus-visible { outline: 2px solid #36c; outline-offset: 2px; }
    .logo { width: 20px; height: 20px; flex: none; }
    .body { padding: .4rem .8rem .8rem; }
    .card { border: 1px solid #c8ccd1; border-radius: 2px; padding: .6rem .7rem; margin: .5rem 0; }
    .card.locatable { cursor: pointer; } .card.locatable:hover { border-color: #36c; }
    .label { color: #a66200; font: bold 12px sans-serif; display: inline-flex; gap: .3rem; align-items: center; }
    /* The "i" next to a finding's label: an icon in the label's colour, still a button for keyboards. */
    .info { all: unset; display: inline-flex; cursor: pointer; color: inherit; }
    .info:focus-visible { outline: 2px solid #36c; outline-offset: 2px; border-radius: 50%; }
    /* Its popover sits under the icon and moves with it (anchor positioning); it flips if there is no room. */
    .numbers[popover] { position: absolute; inset: auto; margin: .4rem 0 0; position-area: bottom span-right;
                        position-try-fallbacks: flip-block, flip-inline; }
    /* The numbers popover: out of the label's bold, coloured text. */
    .numbers { max-width: 380px; padding: .8rem 1rem; border: 1px solid #a2a9b1; border-radius: 2px; box-shadow: 0 4px 16px rgba(0,0,0,.25);
               color: #202122; font: 13px/1.5 sans-serif; }
    .numbers h4 { margin: 0 0 .4rem; font-size: 14px; } .numbers p { margin: .3rem 0; }
    .numbers table { border-collapse: collapse; } .numbers td { padding: 0 1rem 0 0; }
    .numbers td.num { text-align: right; font-variant-numeric: tabular-nums; } .numbers tr.this td { font-weight: bold; }
    /* Keep in sync with the card styles in src/wikicross/index.html. */
    .meta { display: flex; justify-content: space-between; gap: .5rem; align-items: center; flex-wrap: wrap; font-size: 12px; position: relative; }
    .pair { display: inline-flex; gap: .3rem; align-items: center; flex-wrap: wrap; }
    .chip { background: #eaecf0; border-radius: 2px; padding: .05rem .4rem; }
    .card h3 { margin: .35rem 0 .2rem; font: bold 15px/1.35 sans-serif; }
    .card h3.pending { font: italic 13px sans-serif; color: #54595d; }
    .summary { font: 14px/1.55 "Linux Libertine", Georgia, serif; margin: 0 0 .5rem; } .summary:empty { display: none; }
    .verdict { margin: 0 0 .4rem; } .verdict:empty { display: none; } .reason { color: #54595d; font-style: italic; }
    .pending { color: #54595d; font-style: italic; }
    /* Each quote a box: header, text, footer. Rows from the subgrid: a finding's headers line up. */
    .quotes { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .6rem; margin-top: .5rem; }
    .quote { display: grid; grid-row: span 3; grid-template-rows: subgrid; row-gap: .3rem; border: 1px solid #c8ccd1;
             border-radius: 2px; padding: .45rem .6rem; background: #fff; }
    .quote.here { border-color: #36c; }
    .quote.outlier { background: #fdf4e6; border-color: #e8c48f; }
    .quote.linked { outline: 2px solid var(--hl-line); outline-offset: 1px; }
    .quote h4 { margin: 0; font: 12px sans-serif; color: #54595d; display: flex; gap: .35rem; align-items: start; flex-wrap: wrap; }
    .quote h4 b { color: #202122; border-bottom: 3px solid var(--hl-line); }
    .quote blockquote { margin: 0; font: 14px/1.5 "Linux Libertine", Georgia, serif; white-space: pre-wrap; }
    .quote .foot { display: flex; justify-content: space-between; align-items: end; gap: .4rem; }
    .tr { position: relative; display: inline-flex; margin-left: auto; }
    .tr > button { all: unset; display: inline-flex; cursor: pointer; color: #36c; padding: .1rem; border-radius: 2px; }
    .tr > button[aria-pressed="true"] { background: #eaecf0; }
    .tr > button:focus-visible { outline: 2px solid #36c; }
    .tr .tip { display: none; position: absolute; right: 0; bottom: 100%; z-index: 20; width: min(340px, 80vw); margin-bottom: .3rem;
               background: #fff; border: 1px solid #c8ccd1; border-radius: 2px; box-shadow: 0 4px 12px rgba(0,0,0,.15);
               padding: .5rem .7rem; font: 14px/1.5 "Linux Libertine", Georgia, serif; white-space: pre-wrap; color: #202122; }
    .tr:hover .tip, .tr:focus-within .tip { display: block; }
    .context { color: #54595d; }
    .section { color: #54595d; font: bold 11px sans-serif; }
    .expand { display: flex; width: 100%; gap: .3rem; align-items: center; justify-content: center; font: 12px sans-serif; color: #36c;
              background: #eaf3ff; border: 0; padding: .1rem; cursor: pointer; }
    .expand:hover { background: #d5e6ff; } .expand:disabled { opacity: .5; cursor: default; }
    .tools { display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .5rem; }
    /* One colour per quote of a finding: its language name, its highlights, and the description's quotes of it. */
    .c0 { --hl: #e3ecfd; --hl-line: #36c; } .c1 { --hl: #dcf3e6; --hl-line: #14866d; }
    .c2 { --hl: #efe3f8; --hl-line: #8e44ad; } .c3 { --hl: #fde2dc; --hl-line: #c0392b; }
    mark { background: var(--hl, #fef6e7); border-bottom: 2px solid var(--hl-line, #edab00); padding: 0 1px; }
    /* Menus: a card's "+N more" and the language picker. */
    .editions summary { margin: 0; width: fit-content; }
    .editions .langs { position: absolute; left: 0; top: 100%; z-index: 10; width: 100%; max-height: 50vh; overflow: auto; columns: 10em;
                       background: #fff; border: 1px solid #c8ccd1; border-radius: 2px; padding: .5rem .7rem; box-shadow: 0 4px 12px rgba(0,0,0,.15); }
    .editions .langs a, .picker label { display: block; break-inside: avoid; padding: .05rem 0; }
    .picker label { cursor: pointer; }
    .picker .actions { column-span: all; display: flex; gap: .4rem; margin-bottom: .4rem; }
    .filters { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; font-size: 13px; margin: .2rem 0 .4rem; position: relative; }
    .filters .toggle-label { display: inline-flex; gap: .3rem; align-items: center; cursor: pointer; }
    .irrelevant { border-top: 1px dashed #c8ccd1; margin-top: .6rem; }
    a { color: #36c; text-decoration: none; display: inline-flex; gap: .2rem; align-items: center; } a:hover { text-decoration: underline; }
    button.small { font: bold 12px sans-serif; padding: .15rem .5rem; border: 1px solid #a2a9b1; background: #f8f9fa; border-radius: 2px; cursor: pointer;
                   display: inline-flex; gap: .3rem; align-items: center; color: #202122; }
    button.small.primary { background: #36c; border-color: #36c; color: #fff; }
    button.small:disabled { opacity: .5; cursor: default; }
    .close { border: 0; background: none; cursor: pointer; color: #54595d; padding: 0; }
    .muted { color: #54595d; } .error { color: #d33; }
    details summary { cursor: pointer; color: #36c; }
    details.elsewhere > summary { margin-top: .8rem; }
    /* Keep in sync with the spinner in src/wikicross/index.html. */
    .spinner { display: inline-block; width: 1em; height: 1em; border: 2px solid #eaecf0; border-top-color: #36c; border-radius: 50%;
               animation: spin .8s linear infinite; vertical-align: -.15em; flex: none; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 3s; } }
    .loading { display: flex; gap: .7rem; align-items: center; }
    .loading .spinner { width: 1.6rem; height: 1.6rem; border-width: 3px; }
  ` }));
  const toggle = $("button", { className: "toggle quiet", type: "button" }, "WikiCross");
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
  // with src/wikicross/index.html.
  const snippetUrl = (m) => {
    const words = m.sentence.trim().split(/\s+/), enc = (w) => encodeURIComponent(w.join(" ")).replace(/-/g, "%2D");
    const text = words.length <= 6 ? enc(words) : `${enc(words.slice(0, 3))},${enc(words.slice(-3))}`;
    return `https://${m.lang}.wikipedia.org/wiki/${encodeURIComponent(m.title.replace(/ /g, "_"))}#:~:text=${text}`;
  };

  // The numbers behind a finding, in a small window (a popover: a click outside or Escape closes it).
  // Keep in sync with src/wikicross/index.html.
  let anchors = 0;  // each "i" is the anchor its popover is placed by
  function numbers(f) {
    const sigma = (d) => { const r = Math.round(d * 10) / 10; return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toFixed(1)}σ`; };
    const rows = Object.entries(f.deviations || {}).sort((a, b) => b[1] - a[1]);
    const box = $("div", { className: "numbers", popover: "auto" },
      $("h4", { textContent: `How far apart: the ${f.axis} axis` }),
      $("p", { textContent: `Each sentence has a position on this axis: towards +, an edition ${f.ends[0]}; towards −, it ${f.ends[1]}. `
        + "Positions are measured against the language's own sentences, so 1σ is a typical spread within that language." }),
      $("p", { textContent: `${langName(f.lang)} sits ${sigma(f.deviations?.[f.lang] ?? f.deviation)} from the average of the others; a finding needs at least 1.2σ either way. Each edition, from its others' average:` }),
      $("table", {}, ...rows.map(([l, d]) => $("tr", { className: l === f.lang ? "this" : "" },
        $("td", { textContent: langName(l) }), $("td", { className: "num", textContent: sigma(d) })))),
      $("p", { className: "muted", textContent: `The sentences are matched as one statement: their largest cosine distance is ${f.distance.toFixed(2)} `
        + "(0 is the same meaning; up to 0.35 counts)." }));
    const anchor = `--numbers-${++anchors}`;
    box.style.positionAnchor = anchor;
    const info = $("button", { className: "info", type: "button", popoverTargetElement: box, title: "The numbers behind this finding",
                               ariaLabel: "The numbers behind this finding" }, icon("info"));
    info.style.anchorName = anchor;
    return [info, box];
  }

  // Paragraph view ("Show paragraphs"): a quote's whole passage, expanding up and down through the
  // article a few sentences per click. Keep in sync with src/wikicross/index.html.
  const STEP = 3;
  const contextOf = (m) => ({ before: [], after: [], top: [m.seq, 0], bottom: [m.seq, 65535], end: {}, busy: false, error: "" });
  function expandable(m, ctx, quote) {
    const wrap = $("div", { className: "expandable" });
    const button = (dir) => {
      if (ctx.end[dir]) return "";
      const b = $("button", { className: "expand", type: "button", disabled: ctx.busy, title: `Show ${STEP} more sentences ${dir === "up" ? "above" : "below"}` },
        icon(dir === "up" ? "up" : "chevron"), dir === "up" ? "Expand up" : "Expand down");
      b.addEventListener("click", async () => {
        ctx.busy = true; draw();
        const [seq, n] = dir === "up" ? ctx.top : ctx.bottom;
        try {
          const rows = await get("/api/context", { lang: m.lang, page_id: m.page_id, seq, n, direction: dir, count: STEP });
          if (rows.length) {
            if (dir === "up") { ctx.before.unshift(...rows); ctx.top = [rows[0].seq, rows[0].n]; }
            else { ctx.after.push(...rows); ctx.bottom = [rows.at(-1).seq, rows.at(-1).n]; }
          }
          ctx.end[dir] = rows.length < STEP;
          ctx.error = "";
        } catch (err) { ctx.error = `Could not load more: ${err.message}`; }
        ctx.busy = false; draw();
      });
      return b;
    };
    const draw = () => {
      const segments = [...ctx.before.map((r) => ({ ...r, nodes: [r.text] })), { seq: m.seq, heading: m.heading, nodes: quote(), quote: true },
        ...ctx.after.map((r) => ({ ...r, nodes: [r.text] }))];
      const body = $("blockquote", {});
      segments.forEach((s, i) => {
        const prev = segments[i - 1];
        if (prev && s.heading !== prev.heading) body.append("\n", $("span", { className: "section", textContent: `§ ${s.heading || "(intro)"}` }), "\n");
        else if (prev) body.append(s.seq !== prev.seq ? "\n" : " ");
        body.append($("span", { className: s.quote ? "quoted" : "context" }, ...s.nodes));
      });
      wrap.replaceChildren(button("up"), body, button("down"), ctx.error ? $("p", { className: "error", textContent: ctx.error }) : "");
    };
    draw();
    return wrap;
  }

  // Which quote each highlighted part of the description comes from. Keep in sync with linkQuotes() in
  // src/wikicross/index.html.
  function linkQuotes(summary, members, state, quotes) {
    const norm = (s) => s.trim().toLowerCase();
    const marksOf = (p) => [...(state.english[p.lang]?.quote || "").matchAll(/<mark>(.*?)<\/mark>/gs)].map((m) => norm(m[1]))
      .concat((state.phrases[p.lang] || []).map(norm));
    for (const mark of summary.querySelectorAll("mark")) {
      const text = norm(mark.textContent);
      let i = members.findIndex((p) => marksOf(p).includes(text));
      if (i < 0) i = members.findIndex((p) => marksOf(p).some((t) => t.includes(text) || text.includes(t)));
      if (i < 0) continue;
      const p = members[i], box = () => quotes.querySelector(`.quote[data-lang="${p.lang}"]`);
      mark.className = `c${i % 4}`;
      mark.title = `From the ${langName(p.lang)} quote`;
      mark.addEventListener("mouseenter", () => box()?.classList.add("linked"));
      mark.addEventListener("mouseleave", () => box()?.classList.remove("linked"));
    }
  }

  // A finding, as card() in src/wikicross/index.html (keep in sync): AI title, description and English
  // quotes, each quote in a coloured box with its translate button, "Show all" and "Show paragraphs".
  // Here this page's edition comes first, with "Show on page" / "Find in source", and the AI is asked
  // only once the card is scrolled into view (`observe`): the panel lists up to 30 findings.
  function finding(f, dismiss, observe) {
    const state = { english: {}, phrases: {}, original: new Set(), aiDone: false, translating: false, translateError: "",
                    passages: {}, passagesBusy: false, passagesError: "", context: false, all: false,
                    ctx: Object.fromEntries(f.members.map((m) => [m.lang, contextOf(m)])) };
    const outliers = f.outlier ? [f.lang] : [];
    const label = $("span", { className: "label" }, icon("scale"),
      f.outlier ? `Outlier: ${langName(f.lang)}` : "Different framing", ...numbers(f));
    // This edition first (it is the one on the page), then outliers, then the API's order.
    const rank = (m) => (m.lang === lang ? 0 : outliers.includes(m.lang) ? 1 : 2);
    const members = [...f.members].sort((a, b) => rank(a) - rank(b));
    const first = members.slice(0, SHOWN);
    const title = $("h3", { className: "pending" }, spinner(), " Asking the AI how they differ…");
    const summary = $("p", { className: "summary" });
    const verdict = $("p", { className: "verdict" });
    const quotes = $("div", { className: "quotes" });
    const card = $("div", { className: "card" });
    const more = members.length > SHOWN ? $("button", { className: "small", type: "button" }) : null;
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
    const translatePassages = async (pool) => {
      const todo = pool.filter((p) => !(p.lang in state.passages));
      if (!todo.length || state.passagesBusy) return;
      state.passagesBusy = true;
      try {
        Object.assign(state.passages, await post("/api/translate", { texts: Object.fromEntries(todo.map((p) => [p.lang, withMarks(p.text, [p.sentence])])), target: "en" }));
        state.passagesError = "";
      } catch (err) { state.passagesError = `Could not translate the paragraphs: ${err.message}`; }
      state.passagesBusy = false;
      renderQuotes();
    };

    const swap = (p, en, english, original) => {
      if (p.lang === "en") return "";
      if (!state.english[p.lang]) {
        const busy = !state.aiDone || state.translating;
        return busy ? $("span", { className: "pending tr", title: "Translating…" }, spinner()) : "";
      }
      const button = $("button", { type: "button", ariaPressed: String(!en),
        ariaLabel: en ? `Show the original ${langName(p.lang)} quote` : "Show the English translation" }, icon("translate"));
      button.dataset.lang = p.lang;
      button.addEventListener("click", () => {
        if (!state.original.delete(p.lang)) state.original.add(p.lang);
        renderQuotes();
        quotes.querySelector(`button[data-lang="${p.lang}"]`)?.focus();  // the re-render replaced it
      });
      return $("span", { className: "tr" }, button,
        $("div", { className: "tip", role: "tooltip" },
          $("div", { className: "section", textContent: en ? `Original (${langName(p.lang)})` : "English translation" }),
          ...(en ? original() : english())));
    };

    const locate = (find) => { if (!showOnPage(own)) find.replaceChildren(icon("find"), "Not found on this page"); };
    const findButton = () => {
      const find = $("button", { className: "small", type: "button", title: source ? "Select this in the wikitext" : "Highlight this on the page" },
        icon("find"), source ? "Find in source" : "Show on page");
      find.addEventListener("click", () => locate(find));
      return find;
    };

    const renderQuotes = () => {
      const pool = state.all ? members : first;
      translateQuotes(pool);
      if (more) more.replaceChildren(icon("list"), state.all ? "Show fewer" : `Show all ${members.length} editions`, icon(state.all ? "up" : "chevron"));
      const english = (p) => state.english[p.lang] && !state.original.has(p.lang);
      if (state.context) translatePassages(pool.filter(english));
      quotes.replaceChildren(...pool.map((p) => {
        const en = english(p);
        const englishQuote = () => marked(state.english[p.lang].quote);
        const originalQuote = () => marked(withMarks(p.sentence, state.phrases[p.lang]));
        const passage = state.passages[p.lang];
        const quote = state.context && en
          ? $("blockquote", {}, ...(passage ? [$("span", { className: "quoted" }, ...marked(passage))]
              : state.passagesError ? [$("span", { className: "error", textContent: state.passagesError })]
              : [spinner(), " Translating the paragraphs…"]))
          : state.context ? expandable(p, state.ctx[p.lang], () => marked(withMarks(p.text, [p.sentence])))
          : $("blockquote", {}, $("span", { className: "quoted" }, ...(en ? englishQuote() : originalQuote())));
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
      }), ...(state.translateError ? [$("p", { className: "error", textContent: state.translateError })] : []));
    };

    const explain = () => post("/api/explain", { passages: first.map((p) => ({ lang: p.lang, heading: p.heading || "", text: p.text, sentence: p.sentence })) })
      .then((x) => {
        title.className = "";
        title.textContent = x.title;
        for (const [l, q] of Object.entries(x.quotes)) {
          state.english[l] = { quote: q.english, heading: q.heading };
          state.phrases[l] = q.phrases;
        }
        summary.replaceChildren(...marked(x.description));
        linkQuotes(summary, members, state, quotes);
        if (!x.discrepancy) {
          verdict.className = "verdict reason";
          verdict.textContent = "Marked irrelevant by the AI check: these passages do not differ clearly in tone "
            + "or framing. Their distance on the axis comes from other differences, such as the facts they "
            + "include, their length or detail.";
          dismiss(card);
        }
      })
      .catch((err) => {
        title.remove();
        verdict.className = "error";
        verdict.textContent = `AI unavailable, quotes in their original language: ${err.message}`;
      })
      .finally(() => { state.aiDone = true; renderQuotes(); });
    renderQuotes();

    const tools = $("div", { className: "tools" });
    if (more) {
      more.addEventListener("click", () => { state.all = !state.all; renderQuotes(); });
      tools.append(more);
    }
    const context = $("button", { className: "small", type: "button" }, icon("paragraph"), "Show paragraphs", icon("chevron"));
    context.addEventListener("click", () => {
      state.context = !state.context;
      context.replaceChildren(icon("paragraph"), state.context ? "Show sentences" : "Show paragraphs", icon(state.context ? "up" : "chevron"));
      renderQuotes();
    });
    tools.append(context);

    if (own) {
      // The whole card shows this page's quote too; its links, buttons, menus and highlights keep their own action.
      card.classList.add("locatable");
      card.addEventListener("click", (e) => { if (!e.target.closest("a, button, details, mark, .tip")) locate(card.querySelector(".foot button.small")); });
    }
    const rest = members.slice(SHOWN);
    card.append(
      $("div", { className: "meta" },
        $("span", { className: "pair" }, ...first.flatMap((m, i) => [
          i ? icon("pair") : "",
          $("span", { className: "chip" }, $("b", { textContent: langName(m.lang) }))]),
          rest.length ? $("details", { className: "editions" }, $("summary", { textContent: `+${rest.length} more` }),
            $("div", { className: "langs" }, ...rest.map((m) => $("a", { href: snippetUrl(m), target: "_blank", rel: "noopener",
              title: `${m.title} § ${m.heading || "(intro)"}` }, $("b", { textContent: langName(m.lang) }))))) : ""),
        label),
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
    const boxes = sorted.map((l) => $("input", { type: "checkbox", value: l, checked: chosen.has(l) }));
    const button = (text, onClick, primary) => {
      const b = $("button", { className: `small${primary ? " primary" : ""}`, type: "button", textContent: text });
      b.addEventListener("click", onClick);
      return b;
    };
    const apply = button("Apply", () => {
      const langs = boxes.filter((b) => b.checked).map((b) => b.value);
      load({ ...query, langs: langs.length === languages.length ? null : langs });
    }, true);
    const update = () => { apply.disabled = boxes.filter((b) => b.checked).length < 2; };  // a comparison needs two
    const all = (on) => { boxes.forEach((b) => { b.checked = on; }); update(); };
    boxes.forEach((b) => b.addEventListener("change", update));
    const picker = $("details", { className: "editions picker" },
      $("summary", { textContent: query.langs ? `Languages: ${query.langs.length} of ${languages.length}` : `Languages: all ${languages.length}` }),
      $("div", { className: "langs" },
        $("div", { className: "actions" }, button("All", () => all(true)), button("None", () => all(false)), apply),
        ...boxes.map((b) => $("label", {}, b, ` ${langName(b.value)} (${b.value})`))));
    const dialects = $("input", { type: "checkbox", checked: !query.dialects });
    dialects.addEventListener("change", () => load({ ...query, dialects: !dialects.checked }));
    return $("div", { className: "filters" }, picker, $("label", { className: "toggle-label" }, dialects, "Hide dialects"));
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
    toggle.replaceChildren(icon(n ? "alert" : "scale"), `WikiCross · ${n}`);
    toggle.className = n ? "toggle" : "toggle quiet";
    const close = $("button", { className: "close", type: "button", title: "Close", ariaLabel: "Close" }, icon("close"));
    close.addEventListener("click", () => { panel.hidden = true; });
    const body = $("div", { className: "body" });
    // The logo and name open this topic in the web app, in a new tab (background.js knows its address).
    const home = $("button", { className: "home", type: "button", title: "Open this topic in the WikiCross web app" }, logo(), "WikiCross");
    home.addEventListener("click", () => chrome.runtime.sendMessage({ type: "open", title, lang }));
    // Findings the AI check does not confirm leave the list for a hidden one at the end, behind a button.
    const irrelevant = $("div", { className: "irrelevant", hidden: true });
    const reveal = $("button", { className: "small", type: "button", hidden: true, ariaExpanded: "false" });
    let dismissed = 0;
    const relabel = () => reveal.replaceChildren(icon("eye"),
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
      body.append($("p", { className: "muted", textContent: `This version (${langName(lang)}) is not compared: its script is not supported yet. Below, what the others state differently.` }));
    } else if (!data.articles.some((a) => a.lang === lang)) {
      body.append($("p", { className: "muted", textContent: `This version (${langName(lang)}) is left out by the filters. Below, what the others state differently.` }));
    } else if (!n) body.append($("p", { className: "muted", textContent: "Nothing in this edition is framed differently from the other editions." }));
    body.append(...mine.map((f) => finding(f, dismiss, observe)));
    if (elsewhere.length) {
      body.append($("details", { className: "elsewhere" }, $("summary", { textContent: `${elsewhere.length} more between the other editions` }),
        ...elsewhere.map((f) => finding(f, dismiss, observe))));
    }
    body.append(reveal, irrelevant);
    panel.replaceChildren($("header", {}, $("h2", {}, home), close), body);
  }

  function showMessage(text, error) {
    const reset = $("button", { className: "small", type: "button", textContent: "Compare all editions" });
    reset.addEventListener("click", () => load({ langs: null, dialects: true }));
    panel.replaceChildren($("div", { className: "body" }, $("p", { className: error ? "error" : "muted", textContent: text }),
      query.langs || !query.dialects ? reset : ""));
  }

  let requested = false;
  function load(next = query) {
    requested = true;
    query = next;
    toggle.replaceChildren(spinner(), "WikiCross");
    // The server's current stage, polled each second while it works; only the stage is announced.
    const stage = $("span", { textContent: "Looking the topic up…" }), seconds = $("span", { className: "muted", ariaHidden: "true" });
    panel.replaceChildren($("div", { className: "body" }, $("div", { className: "loading" }, spinner(),
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
