// Paragraph view only ("Show paragraphs"), and only in the web app: when a quote's whole passage is not
// enough context, it expands up and down through the article, a few sentences per click, like the
// folded lines of a GitHub diff. Context is muted; a new passage starts a new line, a new section shows
// its heading. `ctx` (contextOf) outlives the component, so a card keeps what it loaded.
import { h, inject } from "vue";
import { CdxButton, CdxIcon, CdxMessage } from "@wikimedia/codex";
import { cdxIconCollapse, cdxIconExpand } from "@wikimedia/codex-icons";
import Marked from "./Marked.js";

const STEP = 3;
export const contextOf = (m) => ({ before: [], after: [], top: [m.seq, 0], bottom: [m.seq, 65535], end: {}, busy: false, error: "" });

export default {
  name: "Expandable",
  props: { member: { type: Object, required: true }, ctx: { type: Object, required: true }, quote: { type: String, required: true } },
  setup(props) {
    const api = inject("api");
    const more = async (dir) => {
      const { ctx, member: m } = props;
      ctx.busy = true;
      const [seq, n] = dir === "up" ? ctx.top : ctx.bottom;
      try {
        const rows = await api.get("/api/context", { lang: m.lang, page_id: m.page_id, seq, n, direction: dir, count: STEP });
        if (rows.length) {
          if (dir === "up") { ctx.before.unshift(...rows); ctx.top = [rows[0].seq, rows[0].n]; }
          else { ctx.after.push(...rows); ctx.bottom = [rows.at(-1).seq, rows.at(-1).n]; }
        }
        ctx.end[dir] = rows.length < STEP;
        ctx.error = "";
      } catch (err) { ctx.error = `Could not load more: ${err.message}`; }
      ctx.busy = false;
    };
    const expander = (dir) => (props.ctx.end[dir] ? null : h(CdxButton, {
      class: "expand", size: "small", weight: "quiet", action: "progressive", disabled: props.ctx.busy,
      title: `Show ${STEP} more sentences ${dir === "up" ? "above" : "below"}`, onClick: () => more(dir),
    }, () => [h(CdxIcon, { icon: dir === "up" ? cdxIconCollapse : cdxIconExpand, size: "small" }), dir === "up" ? "Expand up" : "Expand down"]));
    return () => {
      const { ctx, member: m } = props;
      const segments = [...ctx.before, { seq: m.seq, heading: m.heading, quote: true }, ...ctx.after];
      const body = [];
      segments.forEach((s, i) => {
        const prev = segments[i - 1];
        if (prev && s.heading !== prev.heading) body.push("\n", h("span", { class: "section" }, `§ ${s.heading || "(intro)"}`), "\n");
        else if (prev) body.push(s.seq !== prev.seq ? "\n" : " ");
        body.push(s.quote ? h("span", { class: "quoted" }, h(Marked, { text: props.quote })) : h("span", { class: "context" }, s.text));
      });
      return h("div", { class: "expandable" }, [expander("up"), h("blockquote", body), expander("down"),
        ctx.error ? h(CdxMessage, { type: "error", inline: true }, () => ctx.error) : null]);
    };
  },
};
