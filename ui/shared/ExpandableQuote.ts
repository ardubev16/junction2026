// Paragraph view only ("Show paragraphs"), and only in the web app: when a quote's whole passage is not
// enough context, it expands up and down through the article, a few sentences per click, like the
// folded lines of a GitHub diff. Context is muted; a new passage starts a new line, a new section shows
// its heading. `ctx` (contextOf) outlives the component, so a card keeps what it loaded.
import { defineComponent, h, inject, type PropType, type VNodeChild } from "vue";
import { CdxButton, CdxIcon, CdxMessage } from "@wikimedia/codex";
import { cdxIconCollapse, cdxIconExpand } from "@wikimedia/codex-icons";
import MarkedText from "./MarkedText";
import { API, errorText, type ContextSentence, type Member } from "./types";

const STEP = 3;
type Direction = "up" | "down";
/** What a quote has loaded around it: sentences before and after, and where each end stands. */
export interface Context {
  before: ContextSentence[];
  after: ContextSentence[];
  top: [number, number];
  bottom: [number, number];
  end: Partial<Record<Direction, boolean>>;
  busy: boolean;
  error: string;
}
export const contextOf = (m: Member): Context => ({
  before: [],
  after: [],
  top: [m.seq, 0],
  bottom: [m.seq, 65535],
  end: {},
  busy: false,
  error: "",
});

export default defineComponent({
  name: "ExpandableQuote",
  props: {
    member: { type: Object as PropType<Member>, required: true },
    ctx: { type: Object as PropType<Context>, required: true },
    quote: { type: String, required: true },
  },
  setup(props) {
    const api = inject(API)!;
    const more = async (dir: Direction) => {
      const { ctx, member: m } = props;
      ctx.busy = true;
      const [seq, n] = dir === "up" ? ctx.top : ctx.bottom;
      try {
        const rows = await api.get<ContextSentence[]>("/api/context", {
          lang: m.lang,
          page_id: m.page_id,
          seq,
          n,
          direction: dir,
          count: STEP,
        });
        if (rows.length) {
          if (dir === "up") {
            ctx.before.unshift(...rows);
            ctx.top = [rows[0].seq, rows[0].n];
          } else {
            ctx.after.push(...rows);
            ctx.bottom = [rows[rows.length - 1].seq, rows[rows.length - 1].n];
          }
        }
        ctx.end[dir] = rows.length < STEP;
        ctx.error = "";
      } catch (err) {
        ctx.error = `Could not load more: ${errorText(err)}`;
      }
      ctx.busy = false;
    };
    const expander = (dir: Direction) =>
      props.ctx.end[dir]
        ? null
        : h(
            CdxButton,
            {
              class: "expand",
              size: "small",
              weight: "quiet",
              action: "progressive",
              disabled: props.ctx.busy,
              title: `Show ${STEP} more sentences ${dir === "up" ? "above" : "below"}`,
              onClick: () => more(dir),
            },
            () => [
              h(CdxIcon, { icon: dir === "up" ? cdxIconCollapse : cdxIconExpand, size: "small" }),
              dir === "up" ? "Expand up" : "Expand down",
            ],
          );
    return () => {
      const { ctx, member: m } = props;
      type Segment = { seq: number; heading: string; text?: string; quote?: true };
      const segments: Segment[] = [...ctx.before, { seq: m.seq, heading: m.heading, quote: true }, ...ctx.after];
      const body: VNodeChild[] = [];
      segments.forEach((s, i) => {
        const prev = segments[i - 1];
        if (prev && s.heading !== prev.heading)
          body.push("\n", h("span", { class: "section" }, `§ ${s.heading || "(intro)"}`), "\n");
        else if (prev) body.push(s.seq !== prev.seq ? "\n" : " ");
        body.push(
          s.quote
            ? h("span", { class: "quoted" }, h(MarkedText, { text: props.quote }))
            : h("span", { class: "context" }, s.text),
        );
      });
      return h("div", { class: "expandable" }, [
        expander("up"),
        h("blockquote", body),
        expander("down"),
        ctx.error ? h(CdxMessage, { type: "error", inline: true }, () => ctx.error) : null,
      ]);
    };
  },
});
