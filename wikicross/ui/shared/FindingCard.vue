<!-- A finding, the same in the web app and the extension. The AI (one /api/explain call for the quotes on
     show) gives its kind, title, a description quoting the framing words, and each quote in English with
     those words marked; the original keeps the same words marked. Quotes show in English; each one's
     translate button shows the original on hover and swaps to it on click. Quotes beyond the first
     SHOWN, and paragraphs, are translated when shown. A finding the AI marks irrelevant moves to
     `irrelevantTarget` (a Teleport, so it keeps its state). -->
<script setup>
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { CdxButton, CdxIcon, CdxInfoChip, CdxMessage, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconArticle, cdxIconCollapse, cdxIconExpand, cdxIconLanguage, cdxIconLinkExternal, cdxIconListBullet, cdxIconSearch } from "@wikimedia/codex-icons";
import Marked from "./Marked.js";
import Expandable, { contextOf } from "./Expandable.js";
import NumbersButton from "./NumbersButton.vue";
import { KIND_NAMES, KIND_STATUS, SHOWN, langName, linkMarks, markParts, snippetUrl, withMarks } from "./util.js";

const props = defineProps({
  finding: { type: Object, required: true },
  focusLang: { type: String, default: null },      // the extension's page edition: its quote first
  paragraphs: { type: Boolean, default: false },   // the web app's "Show paragraphs", with expanding context
  lazy: { type: Boolean, default: false },         // ask the AI only once the card is in view…
  observeRoot: { type: Object, default: null },    // …of this scrolling element
  locate: { type: Function, default: null },       // extension: show the page edition's quote on the page
  locateLabel: { type: Object, default: () => ({ text: "Show on page", title: "Highlight this on the page" }) },
  irrelevantTarget: { type: Object, default: null },
});
const emit = defineEmits(["dismiss"]);
const api = inject("api");

const f = props.finding;
const outliers = f.outlier ? [f.lang] : [];
// The page's edition first, then outliers, then the API's order; a card shows the first SHOWN unless expanded.
const rank = (m) => (m.lang === props.focusLang ? 0 : outliers.includes(m.lang) ? 1 : 2);
const members = [...f.members].sort((a, b) => rank(a) - rank(b));
const first = members.slice(0, SHOWN);
const own = members.find((m) => m.lang === props.focusLang);

const ai = reactive({ done: false, title: "", description: "", kind: null, discrepancy: true, error: "" });
const english = reactive({}), phrases = reactive({}), original = reactive(new Set());
const all = ref(false), context = ref(false), dismissed = ref(false), hovered = ref(null), notFound = ref(false);
const translating = ref(false), translateError = ref("");
const passages = reactive({}), passagesBusy = ref(false), passagesError = ref("");
const ctx = reactive(Object.fromEntries(members.map((m) => [m.lang, contextOf(m)])));

const pool = computed(() => (all.value ? members : first));
const inEnglish = (p) => !!english[p.lang] && !original.has(p.lang);
const description = computed(() => linkMarks(markParts(ai.description), members, english, phrases));

// Quotes the AI call does not cover (beyond the first SHOWN, or all if it failed), in one call.
async function translateQuotes() {
  const todo = pool.value.filter((p) => !english[p.lang] && (ai.done || !first.includes(p)));
  if (!todo.length || translating.value) return;
  translating.value = true;
  const texts = {};
  for (const p of todo) {
    texts[p.lang] = p.sentence;
    if (p.heading) texts[`${p.lang}-heading`] = p.heading;
  }
  try {
    const t = await api.post("/api/translate", { texts, target: "en" });
    for (const p of todo) english[p.lang] = { quote: t[p.lang], heading: t[`${p.lang}-heading`] ?? p.heading };
    translateError.value = "";
  } catch (err) { translateError.value = `Could not translate: ${err.message}`; }
  translating.value = false;
  translateQuotes();  // shown meanwhile
}
watch([pool, () => ai.done], translateQuotes);

// Paragraphs in English: the passages translated, the quote marked in them. A finding marked irrelevant
// shows its paragraphs in the original: not worth a translation.
async function translatePassages() {
  if (!context.value || dismissed.value || passagesBusy.value) return;
  const todo = pool.value.filter((p) => inEnglish(p) && !(p.lang in passages));
  if (!todo.length) return;
  passagesBusy.value = true;
  try {
    Object.assign(passages, await api.post("/api/translate", { texts: Object.fromEntries(todo.map((p) => [p.lang, withMarks(p.text, [p.sentence])])), target: "en" }));
    passagesError.value = "";
  } catch (err) { passagesError.value = `Could not translate the paragraphs: ${err.message}`; }
  passagesBusy.value = false;
}
watch(() => [context.value, pool.value.filter(inEnglish).map((p) => p.lang).join()], translatePassages);

function explain() {
  api.post("/api/explain", { passages: first.map((p) => ({ lang: p.lang, heading: p.heading || "", text: p.text, sentence: p.sentence })) })
    .then((x) => {
      for (const [lang, q] of Object.entries(x.quotes)) {
        english[lang] = { quote: q.english, heading: q.heading };
        phrases[lang] = q.phrases;
      }
      Object.assign(ai, { title: x.title, description: x.description, kind: x.kind, discrepancy: x.discrepancy });
      if (!x.discrepancy) { dismissed.value = true; emit("dismiss"); }
    })
    .catch((err) => { ai.error = `AI unavailable, quotes in their original language: ${err.message}`; })
    .finally(() => { ai.done = true; });
}

const card = ref(null);
let observer;
onMounted(() => {
  if (!props.lazy) return explain();
  observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { observer.disconnect(); explain(); }
  }, { root: props.observeRoot });
  observer.observe(card.value);
});
onBeforeUnmount(() => observer?.disconnect());

const doLocate = () => { notFound.value = !props.locate(own); };
// The whole card shows the page's quote too; its links, buttons, menus and highlights keep their own action.
const onCardClick = (e) => {
  if (props.locate && own && !e.target.closest("a, button, mark, .tip, .cdx-popover")) doLocate();
};
const swapQuote = (p) => { if (!original.delete(p.lang)) original.add(p.lang); };
</script>

<template>
  <Teleport defer :to="irrelevantTarget" :disabled="!dismissed || !irrelevantTarget">
    <article ref="card" class="card" :class="{ locatable: locate && own }" @click="onCardClick">
      <div class="meta">
        <CdxInfoChip v-if="ai.done && !ai.discrepancy" :status="KIND_STATUS.none">Irrelevant</CdxInfoChip>
        <CdxInfoChip v-else-if="ai.done && ai.kind" :status="KIND_STATUS[ai.kind]">{{ KIND_NAMES[ai.kind] }}</CdxInfoChip>
        <span class="score">
          <template v-if="f.outlier">Outlier: {{ langName(f.lang) }}</template>
          <NumbersButton :finding="f" />
        </span>
      </div>
      <h3 v-if="!ai.done" class="pending">
        <CdxProgressIndicator>Asking the AI</CdxProgressIndicator> Asking the AI how they differ…
      </h3>
      <h3 v-else-if="ai.title">{{ ai.title }}</h3>
      <CdxMessage v-if="ai.error" type="warning" inline>{{ ai.error }}</CdxMessage>
      <p v-if="ai.done && !ai.discrepancy" class="reason">
        Marked irrelevant by the AI check: these passages neither disagree on facts nor differ clearly in tone or
        framing. Their distance on the axis comes from other differences, such as what they include, their length or detail.
      </p>
      <p v-if="ai.description" class="summary"><Marked :parts="description" @hover="hovered = $event" /></p>

      <div class="quotes">
        <div v-for="p in pool" :key="p.lang" class="quote"
             :class="[`c${members.indexOf(p) % 4}`, { here: p.lang === focusLang, outlier: outliers.includes(p.lang), linked: hovered === p.lang }]">
          <h4>
            <b>{{ langName(p.lang) }}<template v-if="p.lang === focusLang"> · this page</template></b>
            <span class="muted">§ {{ (inEnglish(p) ? english[p.lang].heading : p.heading) || "(intro)" }}</span>
            <a v-if="p.lang !== focusLang" :href="snippetUrl(p)" target="_blank" rel="noopener"
               :title="`Open this quote on Wikipedia: ${p.title}`" :aria-label="`Open this quote on ${langName(p.lang)} Wikipedia`">
              <CdxIcon :icon="cdxIconLinkExternal" size="small" />
            </a>
          </h4>

          <blockquote v-if="context && inEnglish(p) && !dismissed">
            <span v-if="passages[p.lang]" class="quoted"><Marked :text="passages[p.lang]" /></span>
            <span v-else-if="passagesError" class="error">{{ passagesError }}</span>
            <span v-else class="pending"><CdxProgressIndicator>Translating</CdxProgressIndicator> Translating the paragraphs…</span>
          </blockquote>
          <Expandable v-else-if="context" :member="p" :ctx="ctx[p.lang]" :quote="withMarks(p.text, [p.sentence])" />
          <blockquote v-else><span class="quoted"><Marked :text="inEnglish(p) ? english[p.lang].quote : withMarks(p.sentence, phrases[p.lang])" /></span></blockquote>

          <div class="foot">
            <CdxButton v-if="locate && p.lang === focusLang" size="small" :title="locateLabel.title" @click="doLocate">
              <CdxIcon :icon="cdxIconSearch" size="small" /> {{ notFound ? "Not found on this page" : locateLabel.text }}
            </CdxButton>
            <template v-if="p.lang !== 'en'">
              <span v-if="english[p.lang]" class="tr">
                <CdxButton size="small" weight="quiet" :action="inEnglish(p) ? 'default' : 'progressive'" :aria-pressed="String(!inEnglish(p))"
                           :aria-label="inEnglish(p) ? `Show the original ${langName(p.lang)} quote` : 'Show the English translation'"
                           @click="swapQuote(p)">
                  <CdxIcon :icon="cdxIconLanguage" size="small" />
                </CdxButton>
                <div class="tip" role="tooltip">
                  <div class="section">{{ inEnglish(p) ? `Original (${langName(p.lang)})` : "English translation" }}</div>
                  <Marked :text="inEnglish(p) ? withMarks(p.sentence, phrases[p.lang]) : english[p.lang].quote" />
                </div>
              </span>
              <span v-else-if="!ai.done || translating" class="tr" title="Translating…"><CdxProgressIndicator>Translating</CdxProgressIndicator></span>
            </template>
          </div>
        </div>
        <CdxMessage v-if="translateError" type="error" inline>{{ translateError }}</CdxMessage>
      </div>

      <div class="tools">
        <CdxButton v-if="members.length > SHOWN" size="small" @click="all = !all">
          <CdxIcon :icon="cdxIconListBullet" size="small" /> {{ all ? "Show fewer" : `Show all ${members.length} editions` }}
          <CdxIcon :icon="all ? cdxIconCollapse : cdxIconExpand" size="small" />
        </CdxButton>
        <CdxButton v-if="paragraphs" size="small" @click="context = !context">
          <CdxIcon :icon="cdxIconArticle" size="small" /> {{ context ? "Show sentences" : "Show paragraphs" }}
          <CdxIcon :icon="context ? cdxIconCollapse : cdxIconExpand" size="small" />
        </CdxButton>
      </div>
    </article>
  </Teleport>
</template>
