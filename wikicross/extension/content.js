// WikiCross on Wikipedia: where the other language editions frame the same thing differently, or
// contradict this one. In the article view and the edit views. All page text goes in
// through textContent, never innerHTML. Keep in sync with src/wikicross/index.html (see AGENTS.md).
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
  const get = (path, query) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "get", path, params: query }, (reply) => {
      if (chrome.runtime.lastError || !reply) reject(Object.assign(new Error(chrome.runtime.lastError?.message || "No answer from the extension."), { status: 0 }));
      else if (reply.error) reject(Object.assign(new Error(reply.error), { status: reply.status }));
      else resolve(reply.data);
    });
  });

  const host = document.createElement("div");
  host.id = "wikicross-host";
  const root = host.attachShadow({ mode: "open" });
  root.append($("style", { textContent: `
    :host { all: initial; }
    * { box-sizing: border-box; }
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
    .what { font-weight: bold; margin: .2rem 0 .4rem; }
    .member { border-left: 3px solid #eaecf0; padding: .2rem .5rem; margin: .35rem 0; font-family: "Linux Libertine", Georgia, serif; }
    .member.here { border-left-color: #36c; background: #f8f9fa; }
    .member.outlier { border-left-color: #a66200; }
    .who { font: 12px sans-serif; color: #54595d; display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
    .who b { color: #202122; }
    mark { background: #fef6e7; border-bottom: 2px solid #edab00; padding: 0 1px; }
    a { color: #36c; text-decoration: none; display: inline-flex; gap: .2rem; align-items: center; } a:hover { text-decoration: underline; }
    button.small { font: bold 12px sans-serif; padding: .15rem .5rem; border: 1px solid #a2a9b1; background: #f8f9fa; border-radius: 2px; cursor: pointer;
                   display: inline-flex; gap: .3rem; align-items: center; color: #202122; }
    .close { border: 0; background: none; cursor: pointer; color: #54595d; padding: 0; }
    .muted { color: #54595d; } .error { color: #d33; }
    details summary { cursor: pointer; color: #36c; margin-top: .8rem; }
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

  // Where a sentence from the dataset (plain text) lies in `text` (wikitext, or a paragraph's text):
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
  // dataset's plain text: the place where most of its longer words occur together is the anchor. Then
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

  function finding(f) {
    const outliers = new Set(f.outlier ? [f.lang] : []);
    const names = (langs) => langs.length > 3 ? `the ${langs.length} other` : langs.map(langName).join(" and ");
    const others = f.members.map((m) => m.lang).filter((l) => l !== f.lang);
    const what = `The ${langName(f.lang)} edition ${f.deviation > 0 ? f.ends[0] : f.ends[1]} than ${others.length > 3 ? names(others) : `the ${names(others)}`} edition${others.length > 1 ? "s" : ""}.`;
    const label = $("span", { className: "label" }, icon("scale"),
      f.outlier ? `Outlier: ${langName(f.lang)}` : "Different framing", ...numbers(f));
    const card = $("div", { className: "card" }, label, $("div", { className: "what", textContent: what }));
    // This edition first (it is the one on the page), then outliers, then the API's order.
    const rank = (m) => (m.lang === lang ? 0 : outliers.has(m.lang) ? 1 : 2);
    const members = [...f.members].sort((a, b) => rank(a) - rank(b));
    const member = (m) => {
      const who = $("div", { className: "who" }, $("b", { textContent: m.lang === lang ? `This edition (${m.lang})` : `${langName(m.lang)} (${m.lang})` }),
        ` ${m.title} § ${m.heading || "(intro)"}`, outliers.has(m.lang) ? " · outlier" : "");
      if (m.lang !== lang) {
        who.append($("a", { href: snippetUrl(m), target: "_blank", rel: "noopener", title: "Open this quote on Wikipedia" }, "open", icon("link")));
      }
      if (m.lang === lang) {
        const source = textarea && textarea.offsetParent;
        const find = $("button", { className: "small", type: "button", title: source ? "Select this in the wikitext" : "Highlight this on the page" },
          icon("find"), source ? "Find in source" : "Show on page");
        const locate = () => { if (!showOnPage(m)) find.replaceChildren(icon("find"), "Not found on this page"); };
        find.addEventListener("click", locate);
        // The whole card shows it too; its links and buttons keep their own action.
        card.classList.add("locatable");
        card.addEventListener("click", (e) => { if (!e.target.closest("a, button")) locate(); });
        who.append(find);
      }
      return $("div", { className: `member${m.lang === lang ? " here" : ""}${outliers.has(m.lang) ? " outlier" : ""}` }, who,
        $("div", { textContent: m.sentence }));
    };
    card.append(...members.slice(0, SHOWN).map(member));
    if (members.length > SHOWN) {
      const all = $("button", { className: "small", type: "button" }, icon("list"), `Show all ${members.length} editions`);
      all.addEventListener("click", () => all.replaceWith(...members.slice(SHOWN).map(member)));
      card.append(all);
    }
    return card;
  }

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
    if (!data.articles.some((a) => a.lang === lang)) {
      body.append($("p", { className: "muted", textContent: `This edition (${langName(lang)}) is not compared: only Latin- and Cyrillic-script editions are. Below, what the others state differently.` }));
    } else if (!n) body.append($("p", { className: "muted", textContent: "Nothing in this edition is framed differently from the other editions." }));
    body.append(...mine.map((f) => finding(f)));
    if (elsewhere.length) {
      body.append($("details", {}, $("summary", { textContent: `${elsewhere.length} more between the other editions` }),
        ...elsewhere.map((f) => finding(f))));
    }
    panel.replaceChildren($("header", {}, $("h2", {}, home), close), body);
  }

  function showMessage(text, error) {
    panel.replaceChildren($("div", { className: "body" }, $("p", { className: error ? "error" : "muted", textContent: text })));
  }

  let requested = false;
  function load() {
    requested = true;
    const spinner = () => $("span", { className: "spinner", ariaHidden: "true" });
    toggle.replaceChildren(spinner(), "WikiCross");
    // The server's current stage, polled each second while it works; only the stage is announced.
    const stage = $("span", { textContent: "Looking the topic up…" }), seconds = $("span", { className: "muted", ariaHidden: "true" });
    panel.replaceChildren($("div", { className: "body" }, $("div", { className: "loading" }, spinner(),
      $("div", {}, $("div", { role: "status" }, stage, " ", seconds),
        $("p", { className: "muted", textContent: "The first time a topic is asked for, its Latin- and Cyrillic-script editions are fetched and embedded: this can take a few minutes." })))));
    const poll = setInterval(() => get("/api/progress", { title }).then((p) => {
      if (!p.stage) return;
      if (stage.textContent !== `${p.stage}…`) stage.textContent = `${p.stage}…`;
      seconds.textContent = `${p.seconds} s`;
    }).catch(() => {}), 1000);
    get("/api/diff", { title, lang, focus: lang, limit: 30 }).then(render).catch((err) => {
      if (!editing && err.status === 404) return host.remove();  // no other edition: stay out of the way
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
