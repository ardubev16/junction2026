// langdiff on Wikipedia: where the other language editions frame the same thing differently, or
// state a figure very differently. In the article view and the edit views. All page text goes in
// through textContent, never innerHTML. Keep in sync with src/langdiff/index.html (see AGENTS.md).
(() => {
  const HOSTS = ["fi", "sv", "en"];  // the editions the extension runs on (manifest.json matches)
  const DISPLAY = new Intl.DisplayNames(["en"], { type: "language" });
  const langName = (code) => { try { return DISPLAY.of(code); } catch { return code; } };
  const SHOWN = 4;  // editions per card before "Show all", as in the web app
  const lang = location.hostname.split(".")[0];
  const params = new URLSearchParams(location.search);
  const action = params.get("action") || "view";
  const editing = /^(edit|submit)$/.test(action) || /^(edit|editsource)$/.test(params.get("veaction") || "");
  if (!HOSTS.includes(lang) || !(editing || action === "view")) return;
  const title = (params.get("title") || decodeURIComponent(location.pathname.replace(/^\/wiki\//, ""))).replace(/_/g, " ");

  // Icons as SVG: font glyphs show as empty squares where the font lacks them. Constant markup only.
  const ICONS = {
    alert: '<path d="M10 2.5 18.5 17.5h-17z"/><path d="M10 8v4M10 14.8v.2"/>',
    scale: '<path d="M10 3v14M6 17h8M3 6h14M5.5 6 3 12h5zM14.5 6 12 12h5z"/>',
    close: '<path d="m5 5 10 10M15 5 5 15"/>',
    find: '<circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4.5 4.5"/>',
    link: '<path d="M11 3h6v6M17 3l-8 8M14 12v5H3V6h5"/>',
  };
  const icon = (name) => {
    const t = document.createElement("template");
    t.innerHTML = `<svg class="icon" viewBox="0 0 20 20" aria-hidden="true">${ICONS[name]}</svg>`;
    return t.content.firstChild;
  };
  const $ = (tag, attrs = {}, ...kids) => {
    const el = Object.assign(document.createElement(tag), attrs);
    el.append(...kids);
    return el;
  };
  // Text with the given phrases wrapped in <mark>, as DOM nodes.
  const marked = (text, phrases = []) => {
    const found = [...new Set(phrases)].filter(Boolean);
    if (!found.length) return [text];
    const re = new RegExp(`(${found.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "g");
    return text.split(re).map((piece, i) => (i % 2 ? $("mark", { textContent: piece }) : piece));
  };
  const get = (path, query) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "get", path, params: query }, (reply) => {
      if (chrome.runtime.lastError || !reply) reject(Object.assign(new Error(chrome.runtime.lastError?.message || "No answer from the extension."), { status: 0 }));
      else if (reply.error) reject(Object.assign(new Error(reply.error), { status: reply.status }));
      else resolve(reply.data);
    });
  });

  const host = document.createElement("div");
  host.id = "langdiff-host";
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
    header { position: sticky; top: 0; background: #f8f9fa; border-bottom: 1px solid #c8ccd1; padding: .6rem .8rem; display: flex; justify-content: space-between; gap: .5rem; }
    header h2 { margin: 0; font: bold 15px/1.3 sans-serif; }
    header p { margin: .2rem 0 0; color: #54595d; font-size: 12px; }
    .body { padding: .4rem .8rem .8rem; }
    .card { border: 1px solid #c8ccd1; border-radius: 2px; padding: .6rem .7rem; margin: .5rem 0; }
    .card.locatable { cursor: pointer; } .card.locatable:hover { border-color: #36c; }
    .label { color: #a66200; font: bold 12px sans-serif; display: inline-flex; gap: .3rem; align-items: center; }
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
    /* Keep in sync with the spinner in src/langdiff/index.html. */
    .spinner { display: inline-block; width: 1em; height: 1em; border: 2px solid #eaecf0; border-top-color: #36c; border-radius: 50%;
               animation: spin .8s linear infinite; vertical-align: -.15em; flex: none; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 3s; } }
    .loading { display: flex; gap: .7rem; align-items: center; }
    .loading .spinner { width: 1.6rem; height: 1.6rem; border-width: 3px; }
  ` }));
  const toggle = $("button", { className: "toggle quiet", type: "button" }, "langdiff");
  const panel = $("section", { className: "panel", hidden: true });
  root.append(toggle, panel);
  document.body.append(host);
  // The page highlight: a CSS Custom Highlight over the paragraph, so the page's DOM (and VisualEditor's
  // model of it) is never touched.
  document.head.append($("style", { textContent: "::highlight(langdiff) { background-color: #fef6e7; text-decoration: underline 2px #edab00; }" }));

  const textarea = document.getElementById("wpTextbox1");
  const words = (text) => [...new Set(text.toLowerCase().match(/[\p{L}\d]{4,}/gu) || [])];

  // Find a sentence from the dataset (plain text) in the wikitext, which adds [[links]], '''bold''' and
  // <ref>s: the place where most of the sentence's longer words occur together wins. Then select the
  // figure in question near it, or else the whole line (a wikitext paragraph).
  function findInSource(sentence, numbers) {
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
    let range = null;
    for (const n of numbers) {  // the number nearest the anchor, as written or with any separator ("126&nbsp;875")
      const re = new RegExp(n.replace(/\D/g, "").split("").join("(?:[\\s\\u00a0\\u202f,.]|&nbsp;)?"), "g");
      let hit = null;
      for (const m of src.matchAll(re)) if (!hit || Math.abs(m.index - best.start) < Math.abs(hit.index - best.start)) hit = m;
      if (hit && Math.abs(hit.index - best.start) < 1500) { range = [hit.index, hit.index + hit[0].length]; break; }
    }
    if (!range) {
      const end = src.indexOf("\n", best.start);
      range = [src.lastIndexOf("\n", best.start) + 1, end === -1 ? src.length : end];
    }
    // Put the caret there first so the browser scrolls the textarea to it, then select.
    textarea.focus();
    textarea.setSelectionRange(range[0], range[0]);
    textarea.blur();
    textarea.focus();
    textarea.setSelectionRange(...range);
    textarea.scrollIntoView({ block: "center" });
    return true;
  }

  // Find the paragraph (or list item, table cell) of the rendered page, in the article view or
  // VisualEditor, holding most of the sentence's longer words, and the figure in question if any
  // (a whole passage spans several paragraphs: the figure picks the right one); highlight and scroll to it.
  function findOnPage(sentence, numbers) {
    const page = document.querySelector(".ve-ce-surface") || document.getElementById("mw-content-text");
    const all = words(sentence);
    const figures = numbers.map((n) => new RegExp(`(?<!\\d)${n.replace(/\D/g, "")}(?!\\d)`));
    let best = null;
    for (const el of page?.querySelectorAll("p, li, dd, td, th, blockquote, figcaption") || []) {
      const text = el.textContent.toLowerCase();
      const plain = text.replace(/(\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))/g, "$1");  // "95 348" -> "95348"
      const score = all.filter((w) => text.includes(w)).length + (figures.some((re) => re.test(plain)) ? 100 : 0);
      // ties go to the shorter element: the cell, not the row's nested list holding it
      if (score && (!best || score > best.score || (score === best.score && text.length < best.length))) best = { el, score, length: text.length };
    }
    if (!best || best.score < Math.max(2, all.length * 0.4)) return false;
    const range = new Range();
    range.selectNodeContents(best.el);
    CSS.highlights.set("langdiff", new Highlight(range));
    best.el.scrollIntoView({ block: "center", behavior: "smooth" });
    return true;
  }

  const showOnPage = (text, numbers) => (textarea && textarea.offsetParent ? findInSource(text, numbers) : findOnPage(text, numbers));

  function finding(f, articles) {
    const urls = Object.fromEntries(articles.map((a) => [a.lang, a.url]));
    const outliers = f.kind === "value" ? new Set(f.slots.flatMap((s) => s.outliers)) : new Set(f.outlier ? [f.lang] : []);
    const names = (langs) => langs.length > 3 ? `the ${langs.length} other` : langs.map(langName).join(" and ");
    let what, label;
    if (f.kind === "value") {
      what = f.slots.map((s) => {
        const byValue = new Map();
        for (const [l, w] of Object.entries(s.values)) {
          const key = w.replace(/\D/g, "");
          byValue.set(key, { w: byValue.get(key)?.w ?? w, langs: [...(byValue.get(key)?.langs ?? []), l] });
        }
        return [...byValue.values()].map(({ w, langs }) => `${w} (${langs.join(", ")})`).join(" vs ");
      }).join(" · ");
      label = $("span", { className: "label" }, icon("alert"),
        `${outliers.size > 3 ? `Outliers: ${outliers.size} editions` : outliers.size ? `Outlier: ${names([...outliers])}` : "Different value"} · ${Math.round(f.change * 100)}% apart`);
    } else {
      const others = f.members.map((m) => m.lang).filter((l) => l !== f.lang);
      what = `The ${langName(f.lang)} edition ${f.deviation > 0 ? f.ends[0] : f.ends[1]} than ${others.length > 3 ? names(others) : `the ${names(others)}`} edition${others.length > 1 ? "s" : ""}.`;
      label = $("span", { className: "label" }, icon("scale"), `${f.outlier ? `Outlier: ${langName(f.lang)}` : "Different framing"} · ${Math.abs(f.deviation).toFixed(1)}σ`);
    }
    const values = (l) => (f.kind === "value" ? f.slots.map((s) => s.values[l]).filter(Boolean) : []);
    const card = $("div", { className: "card" }, label, $("div", { className: "what", textContent: what }));
    // This edition first (it is the one on the page), then outliers, then the API's order.
    const rank = (m) => (m.lang === lang ? 0 : outliers.has(m.lang) ? 1 : 2);
    const members = [...f.members].sort((a, b) => rank(a) - rank(b));
    const member = (m) => {
      const text = m.sentence ?? m.text;
      const who = $("div", { className: "who" }, $("b", { textContent: m.lang === lang ? `This edition (${m.lang})` : `${langName(m.lang)} (${m.lang})` }),
        ` ${m.title} § ${m.heading || "(intro)"}`, outliers.has(m.lang) ? " · outlier" : "");
      if (m.lang !== lang && /^https?:\/\//.test(urls[m.lang] || "")) {
        who.append($("a", { href: urls[m.lang], target: "_blank", rel: "noopener" }, "open", icon("link")));
      }
      if (m.lang === lang) {
        const source = textarea && textarea.offsetParent;
        const find = $("button", { className: "small", type: "button", title: source ? "Select this in the wikitext" : "Highlight this paragraph on the page" },
          icon("find"), source ? "Find in source" : "Show on page");
        const locate = () => { if (!showOnPage(text, values(m.lang))) find.replaceChildren(icon("find"), "Not found on this page"); };
        find.addEventListener("click", locate);
        // The whole card shows it too; its links and buttons keep their own action.
        card.classList.add("locatable");
        card.addEventListener("click", (e) => { if (!e.target.closest("a, button")) locate(); });
        who.append(find);
      }
      return $("div", { className: `member${m.lang === lang ? " here" : ""}${outliers.has(m.lang) ? " outlier" : ""}` }, who,
        $("div", {}, ...marked(text, values(m.lang))));
    };
    card.append(...members.slice(0, SHOWN).map(member));
    if (members.length > SHOWN) {
      const all = $("button", { className: "small", type: "button" }, `Show all ${members.length} editions`);
      all.addEventListener("click", () => all.replaceWith(...members.slice(SHOWN).map(member)));
      card.append(all);
    }
    return card;
  }

  function render(data) {
    const mine = data.differences.filter((f) => f.members.some((m) => m.lang === lang));
    const elsewhere = data.differences.filter((f) => !mine.includes(f));
    const others = data.articles.length > 4 ? `${data.articles.length - 1} other editions`
      : data.articles.filter((a) => a.lang !== lang).map((a) => a.lang).join(", ");
    const n = mine.length;
    toggle.replaceChildren(icon(n ? "alert" : "scale"), `langdiff · ${n}`);
    toggle.className = n ? "toggle" : "toggle quiet";
    const close = $("button", { className: "close", type: "button", title: "Close" }, icon("close"));
    close.addEventListener("click", () => { panel.hidden = true; });
    const body = $("div", { className: "body" });
    if (!n) body.append($("p", { className: "muted", textContent: "Nothing in this edition is framed differently or states a figure very differently from the other editions." }));
    body.append(...mine.map((f) => finding(f, data.articles)));
    if (elsewhere.length) {
      body.append($("details", {}, $("summary", { textContent: `${elsewhere.length} more between the other editions` }),
        ...elsewhere.map((f) => finding(f, data.articles))));
    }
    panel.replaceChildren(
      $("header", {}, $("div", {}, $("h2", { textContent: "Where other editions disagree" }),
        $("p", { textContent: `${title}: compared with ${others || "no other edition"}. Not the text on this page: fi, sv and en come from the dataset snapshot (August 2025), other editions from when the topic was first asked for. Click a finding to show it on the page.` })), close),
      body);
  }

  function showMessage(text, error) {
    panel.replaceChildren($("div", { className: "body" }, $("p", { className: error ? "error" : "muted", textContent: text })));
  }

  let requested = false;
  function load() {
    requested = true;
    const spinner = () => $("span", { className: "spinner", ariaHidden: "true" });
    toggle.replaceChildren(spinner(), "langdiff");
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
      toggle.replaceChildren(err.status ? "langdiff · –" : "langdiff · ?");
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
