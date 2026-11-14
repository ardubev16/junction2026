// langdiff in the Wikipedia edit view: where the other language editions state different figures,
// or frame the same thing differently. All page text goes in through textContent, never innerHTML.
(() => {
  const LANGS = { fi: "Finnish", sv: "Swedish", en: "English" };
  const lang = location.hostname.split(".")[0];
  const params = new URLSearchParams(location.search);
  const editing = /^(edit|submit)$/.test(params.get("action") || "") || /^(edit|editsource)$/.test(params.get("veaction") || "");
  if (!(lang in LANGS) || !editing) return;
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
    h3 { font: bold 13px sans-serif; color: #54595d; text-transform: uppercase; letter-spacing: .04em; margin: .8rem 0 .3rem; }
    .card { border: 1px solid #c8ccd1; border-radius: 2px; padding: .6rem .7rem; margin: .5rem 0; }
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
  ` }));
  const toggle = $("button", { className: "toggle quiet", type: "button" }, "langdiff …");
  const panel = $("section", { className: "panel", hidden: true });
  toggle.addEventListener("click", () => { panel.hidden = !panel.hidden; });
  root.append(toggle, panel);
  document.body.append(host);

  const textarea = document.getElementById("wpTextbox1");

  // Find a sentence from the dataset (plain text) in the wikitext, which adds [[links]], '''bold''' and
  // <ref>s: the place where most of the sentence's longer words occur together wins. Then select the
  // number in question near it, or the anchor word.
  function findInSource(sentence, numbers) {
    const src = textarea.value;
    const words = [...new Set(sentence.toLowerCase().match(/[\p{L}\d]{4,}/gu) || [])];
    const anchors = [...words].sort((a, b) => b.length - a.length).slice(0, 3);
    const lower = src.toLowerCase();
    let best = null;
    for (const anchor of anchors) {
      for (let i = lower.indexOf(anchor); i !== -1; i = lower.indexOf(anchor, i + 1)) {
        const near = lower.slice(Math.max(0, i - 300), i + 300);
        const score = words.filter((w) => near.includes(w)).length;
        if (!best || score > best.score) best = { score, start: i, end: i + anchor.length };
      }
    }
    if (!best) return false;
    for (const n of numbers) {  // the number nearest the anchor, as written or with any separator
      const re = new RegExp(n.replace(/\D/g, "").split("").join("[\\s\\u00a0\\u202f,.]?"), "g");
      let hit = null;
      for (const m of src.matchAll(re)) if (!hit || Math.abs(m.index - best.start) < Math.abs(hit.index - best.start)) hit = m;
      if (hit && Math.abs(hit.index - best.start) < 1500) { best = { start: hit.index, end: hit.index + hit[0].length }; break; }
    }
    // Put the caret there first so the browser scrolls the textarea to it, then select.
    textarea.focus();
    textarea.setSelectionRange(best.start, best.start);
    textarea.blur();
    textarea.focus();
    textarea.setSelectionRange(best.start, best.end);
    textarea.scrollIntoView({ block: "center" });
    return true;
  }

  function finding(f, kind, articles) {
    const urls = Object.fromEntries(articles.map((a) => [a.lang, a.url]));
    const outliers = kind === "figures" ? new Set(f.slots.flatMap((s) => s.outliers)) : new Set(f.outlier ? [f.lang] : []);
    let what, label;
    if (kind === "figures") {
      what = f.slots.map((s) => {
        const byValue = new Map();
        for (const [l, w] of Object.entries(s.values)) {
          const key = w.replace(/\D/g, "");
          byValue.set(key, { w: byValue.get(key)?.w ?? w, langs: [...(byValue.get(key)?.langs ?? []), l] });
        }
        return [...byValue.values()].map(({ w, langs }) => `${w} (${langs.join(", ")})`).join(" vs ");
      }).join(" · ");
      label = $("span", { className: "label" }, icon("alert"), outliers.size ? `Different figures · outlier: ${[...outliers].map((l) => LANGS[l]).join(", ")}` : "Different figures");
    } else {
      const others = f.members.map((m) => m.lang).filter((l) => l !== f.lang).map((l) => LANGS[l]).join(" and ");
      what = `The ${LANGS[f.lang]} edition ${f.deviation > 0 ? f.ends[0] : f.ends[1]} than the ${others} edition${f.members.length > 2 ? "s" : ""}.`;
      label = $("span", { className: "label" }, icon("scale"), `Different framing · ${Math.abs(f.deviation).toFixed(1)}σ`);
    }
    const values = (l) => (kind === "figures" ? f.slots.map((s) => s.values[l]).filter(Boolean) : []);
    // This edition first: it is the one being edited.
    const members = [...f.members].sort((a, b) => (b.lang === lang) - (a.lang === lang));
    return $("div", { className: "card" }, label, $("div", { className: "what", textContent: what }),
      ...members.map((m) => {
        const text = m.sentence ?? m.text;
        const who = $("div", { className: "who" }, $("b", { textContent: m.lang === lang ? `This edition (${m.lang})` : `${LANGS[m.lang]} (${m.lang})` }),
          ` ${m.title} § ${m.heading || "(intro)"}`, outliers.has(m.lang) ? " · outlier" : "");
        if (m.lang !== lang && /^https?:\/\//.test(urls[m.lang] || "")) {
          who.append($("a", { href: urls[m.lang], target: "_blank", rel: "noopener" }, "open", icon("link")));
        }
        if (m.lang === lang && textarea) {
          const find = $("button", { className: "small", type: "button", title: "Select this in the wikitext" }, icon("find"), "Find in source");
          find.addEventListener("click", () => { if (!findInSource(text, values(m.lang))) find.textContent = "Not found in source"; });
          who.append(find);
        }
        return $("div", { className: `member${m.lang === lang ? " here" : ""}${outliers.has(m.lang) ? " outlier" : ""}` }, who,
          $("div", {}, ...marked(text, values(m.lang))));
      }));
  }

  function render(data) {
    const mine = (f) => f.members.some((m) => m.lang === lang);
    const figures = data.figures.filter(mine), framing = data.framing.filter(mine);
    const elsewhere = data.figures.length + data.framing.length - figures.length - framing.length;
    const others = data.articles.filter((a) => a.lang !== lang).map((a) => a.lang).join(", ");
    const n = figures.length + framing.length;
    toggle.replaceChildren(icon(n ? "alert" : "scale"), `langdiff · ${n}`);
    toggle.className = n ? "toggle" : "toggle quiet";
    const close = $("button", { className: "close", type: "button", title: "Close" }, icon("close"));
    close.addEventListener("click", () => { panel.hidden = true; });
    const body = $("div", { className: "body" });
    if (!n) body.append($("p", { className: "muted", textContent: "No figures or framing in this edition differ from the other editions." }));
    if (figures.length) body.append($("h3", { textContent: "Different figures" }), ...figures.map((f) => finding(f, "figures", data.articles)));
    if (framing.length) body.append($("h3", { textContent: "Different framing" }), ...framing.map((f) => finding(f, "framing", data.articles)));
    if (elsewhere) {
      body.append($("details", {}, $("summary", { textContent: `${elsewhere} more between the other editions` }),
        ...data.figures.filter((f) => !mine(f)).map((f) => finding(f, "figures", data.articles)),
        ...data.framing.filter((f) => !mine(f)).map((f) => finding(f, "framing", data.articles))));
    }
    panel.replaceChildren(
      $("header", {}, $("div", {}, $("h2", { textContent: "Where other editions disagree" }),
        $("p", { textContent: `${title}: compared with ${others || "no other edition"}. Based on the dataset snapshot (August 2025), not the text being edited.` })), close),
      body);
  }

  function showMessage(text, error) {
    panel.replaceChildren($("div", { className: "body" }, $("p", { className: error ? "error" : "muted", textContent: text })));
  }

  showMessage("Comparing the editions… the first time an article is asked for, it is embedded: this can take a few minutes.");
  chrome.runtime.sendMessage({ type: "diff", title }, (reply) => {
    if (chrome.runtime.lastError || !reply) {
      toggle.replaceChildren("langdiff · ?");
      return showMessage(chrome.runtime.lastError?.message || "No answer from the extension.", true);
    }
    if (reply.error) {
      toggle.replaceChildren("langdiff · –");
      return showMessage(reply.error, true);
    }
    render(reply.data);
  });
})();
