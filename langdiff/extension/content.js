// langdiff on Wikipedia: where the other language editions frame the same thing differently, or
// state a figure very differently. In the article view and the edit views. All page text goes in
// through textContent, never innerHTML. Keep in sync with src/langdiff/index.html (see AGENTS.md).
(() => {
  const LANGS = { fi: "Finnish", sv: "Swedish", en: "English" };
  const lang = location.hostname.split(".")[0];
  const params = new URLSearchParams(location.search);
  const action = params.get("action") || "view";
  const editing = /^(edit|submit)$/.test(action) || /^(edit|editsource)$/.test(params.get("veaction") || "");
  if (!(lang in LANGS) || !(editing || action === "view")) return;
  const title = (params.get("title") || decodeURIComponent(location.pathname.replace(/^\/wiki\//, ""))).replace(/_/g, " ");

  // Icons as SVG: font glyphs show as empty squares where the font lacks them. Constant markup only.
  const ICONS = {
    alert: '<path d="M10 2.5 18.5 17.5h-17z"/><path d="M10 8v4M10 14.8v.2"/>',
    scale: '<path d="M10 3v14M6 17h8M3 6h14M5.5 6 3 12h5zM14.5 6 12 12h5z"/>',
    close: '<path d="m5 5 10 10M15 5 5 15"/>',
    find: '<circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4.5 4.5"/>',
    link: '<path d="M11 3h6v6M17 3l-8 8M14 12v5H3V6h5"/>',
    chevron: '<path d="m5 8 5 5 5-5"/>',
    up: '<path d="m5 12 5-5 5 5"/>',
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
    .member blockquote { margin: 0; white-space: pre-wrap; }
    .context { color: #54595d; }
    .section { color: #54595d; font: bold 11px sans-serif; }
    .expand { display: flex; width: 100%; gap: .3rem; align-items: center; justify-content: center; font: 11px sans-serif; color: #36c;
              background: #eaf3ff; border: 0; padding: .05rem; margin: .15rem 0; cursor: pointer; }
    .expand:hover { background: #d5e6ff; } .expand:disabled { opacity: .5; cursor: default; }
    .who { font: 12px sans-serif; color: #54595d; display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
    .who b { color: #202122; }
    mark { background: #fef6e7; border-bottom: 2px solid #edab00; padding: 0 1px; }
    a { color: #36c; text-decoration: none; display: inline-flex; gap: .2rem; align-items: center; } a:hover { text-decoration: underline; }
    button.small { font: bold 12px sans-serif; padding: .15rem .5rem; border: 1px solid #a2a9b1; background: #f8f9fa; border-radius: 2px; cursor: pointer;
                   display: inline-flex; gap: .3rem; align-items: center; color: #202122; }
    .close { border: 0; background: none; cursor: pointer; color: #54595d; padding: 0; }
    .muted { color: #54595d; } .error { color: #d33; }
    details summary { cursor: pointer; color: #36c; margin-top: .8rem; }
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

  // Keep in sync with expandable() in src/langdiff/index.html.
  // A quote that expands up and down through its article, a few sentences per click, like the folded
  // lines of a GitHub diff. Context is muted; a new passage starts a new line, a new section shows its
  // heading.
  const STEP = 3;
  function expandable(m, quote) {
    const ctx = { before: [], after: [], top: [m.seq, m.n ?? 0], bottom: [m.seq, m.n ?? 65535], end: {}, busy: false, error: "" };
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

  function finding(f, articles) {
    const urls = Object.fromEntries(articles.map((a) => [a.lang, a.url]));
    const outliers = f.kind === "value" ? new Set(f.slots.flatMap((s) => s.outliers)) : new Set(f.outlier ? [f.lang] : []);
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
        `${outliers.size ? `Outlier: ${[...outliers].map((l) => LANGS[l]).join(", ")}` : "Different value"} · ${Math.round(f.change * 100)}% apart`);
    } else {
      const others = f.members.map((m) => m.lang).filter((l) => l !== f.lang).map((l) => LANGS[l]).join(" and ");
      what = `The ${LANGS[f.lang]} edition ${f.deviation > 0 ? f.ends[0] : f.ends[1]} than the ${others} edition${f.members.length > 2 ? "s" : ""}.`;
      label = $("span", { className: "label" }, icon("scale"), `${f.outlier ? `Outlier: ${LANGS[f.lang]}` : "Different framing"} · ${Math.abs(f.deviation).toFixed(1)}σ`);
    }
    const values = (l) => (f.kind === "value" ? f.slots.map((s) => s.values[l]).filter(Boolean) : []);
    const card = $("div", { className: "card" }, label, $("div", { className: "what", textContent: what }));
    // This edition first: it is the one on the page.
    const members = [...f.members].sort((a, b) => (b.lang === lang) - (a.lang === lang));
    for (const m of members) {
      const text = m.sentence ?? m.text;
      const who = $("div", { className: "who" }, $("b", { textContent: m.lang === lang ? `This edition (${m.lang})` : `${LANGS[m.lang]} (${m.lang})` }),
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
      card.append($("div", { className: `member${m.lang === lang ? " here" : ""}${outliers.has(m.lang) ? " outlier" : ""}` }, who,
        expandable(m, () => marked(text, values(m.lang)))));
    }
    return card;
  }

  function render(data) {
    const mine = data.differences.filter((f) => f.members.some((m) => m.lang === lang));
    const elsewhere = data.differences.filter((f) => !mine.includes(f));
    const others = data.articles.filter((a) => a.lang !== lang).map((a) => a.lang).join(", ");
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
        $("p", { textContent: `${title}: compared with ${others || "no other edition"}. Based on the dataset snapshot (August 2025), not the text on this page. Click a finding to show it on the page.` })), close),
      body);
  }

  function showMessage(text, error) {
    panel.replaceChildren($("div", { className: "body" }, $("p", { className: error ? "error" : "muted", textContent: text })));
  }

  let requested = false;
  function load() {
    requested = true;
    toggle.replaceChildren("langdiff …");
    showMessage("Comparing the editions… the first time an article is asked for, it is embedded: this can take a few minutes.");
    get("/api/diff", { title, limit: 30 }).then(render).catch((err) => {
      if (!editing && err.status === 404) return host.remove();  // not an article in the dataset: stay out of the way
      toggle.replaceChildren(err.status ? "langdiff · –" : "langdiff · ?");
      showMessage(err.message, true);
    });
  }
  toggle.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!requested) load();
  });
  // In the edit views at once; in the article view only when asked, so that reading Wikipedia does
  // not embed every article visited.
  if (editing) load();
})();
