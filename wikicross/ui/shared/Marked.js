// Text with <mark>s (see markParts), as text nodes and <mark> elements, never as HTML. A mark linked to
// a quote (linkMarks) takes the quote's colour, names it on hover and reports the hover.
import { h } from "vue";
import { langName, markParts } from "./util.js";

export default {
  name: "Marked",
  props: { text: { type: String, default: "" }, parts: { type: Array, default: null } },
  emits: ["hover"],
  setup(props, { emit }) {
    return () => (props.parts || markParts(props.text)).map((p) => (!p.mark ? p.text : h("mark", {
      class: p.quote != null ? `c${p.quote % 4}` : null,
      title: p.lang ? `From the ${langName(p.lang)} quote` : null,
      onMouseenter: () => p.lang && emit("hover", p.lang),
      onMouseleave: () => p.lang && emit("hover", null),
    }, p.text)));
  },
};
