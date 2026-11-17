<!-- A finding, the same in the web app and the extension. Its AI explanation of the first SHOWN quotes
     comes with it (/api/diff, ai=true) or is asked for once the card nears the view (/api/explain, by
     the quotes' place): its kind, title, a description quoting the framing words, and
     each quote in English with those words marked; the original keeps the same words marked. Quotes show
     in English; each one's translate button shows the original on hover and swaps to it on click. Quotes
     beyond the first SHOWN (all of them if the AI failed), and paragraphs, are translated when shown, by
     their place: the server reads their text. A finding the AI marks irrelevant moves to
     `irrelevantTarget` (a Teleport, so it keeps its state). -->
<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { CdxButton, CdxIcon, CdxInfoChip, CdxMessage, CdxProgressIndicator } from "@wikimedia/codex";
import {
  cdxIconArticle,
  cdxIconCollapse,
  cdxIconExpand,
  cdxIconLanguage,
  cdxIconLinkExternal,
  cdxIconListBullet,
  cdxIconSearch,
} from "@wikimedia/codex-icons";
import MarkedText from "./MarkedText";
import ExpandableQuote, { contextOf } from "./ExpandableQuote";
import NumbersButton from "./NumbersButton.vue";
import { API, errorText, type English, type Explanation, type Finding, type Member } from "./types";
import { KIND_NAMES, KIND_STATUS, SHOWN, langName, linkMarks, markParts, snippetUrl, withMarks } from "./util";

const props = withDefaults(
  defineProps<{
    finding: Finding;
    focusLang?: string | null; // the extension's page edition: its quote first
    observeRoot?: HTMLElement | null; // the scrolling element, for a card the AI explains when near view
    paragraphs?: boolean; // the web app's "Show paragraphs", with expanding context
    locate?: ((m: Member) => boolean) | null; // extension: show the page edition's quote on the page
    locateLabel?: { text: string; title: string };
    irrelevantTarget?: HTMLElement | null;
  }>(),
  {
    focusLang: null,
    observeRoot: null,
    paragraphs: false,
    locate: null,
    locateLabel: () => ({ text: "Show on page", title: "Highlight this on the page" }),
    irrelevantTarget: null,
  },
);
const emit = defineEmits<{ dismiss: [] }>();
const api = inject(API)!;

const f = props.finding;
const outliers = f.outlier ? [f.lang] : [];
// In the API's order (the page's edition first, then the outlier); a card shows the first SHOWN unless expanded.
const members = f.members;
const first = members.slice(0, SHOWN);
const own = members.find((m) => m.lang === props.focusLang);

// The AI's explanation: with the finding (/api/diff, ai=true), else asked for once the card nears the
// view. If it failed, the quotes stay in their language until translated.
const ai = ref<Explanation | null>(null),
  aiError = ref(""),
  settled = ref(false);
const english = reactive<English>({}),
  phrases = reactive<Record<string, string[]>>({}),
  original = reactive(new Set<string>());
const all = ref(false),
  context = ref(false),
  dismissed = ref(false),
  hovered = ref<string | null>(null),
  notFound = ref(false);
const translating = ref(false),
  translateError = ref("");
const passages = reactive<Record<string, string>>({}),
  passagesBusy = ref(false),
  passagesError = ref("");
const ctx = reactive(Object.fromEntries(members.map((m) => [m.lang, contextOf(m)])));

const pool = computed(() => (all.value ? members : first));
const inEnglish = (p: Member) => !!english[p.lang] && !original.has(p.lang);
const description = computed(() => linkMarks(markParts(ai.value?.description), members, english, phrases));
const place = ({ lang, page_id, seq, n }: Member) => ({ lang, page_id, seq, n });

function settle(x: Explanation | { error: string }) {
  if ("error" in x) aiError.value = `AI unavailable, quotes in their original language: ${x.error}`;
  else {
    ai.value = x;
    for (const [lang, q] of Object.entries(x.quotes)) {
      english[lang] = { quote: q.english, heading: q.heading };
      phrases[lang] = q.phrases;
    }
    if (!x.discrepancy) {
      dismissed.value = true;
      emit("dismiss");
    }
  }
  settled.value = true;
}
const card = ref<HTMLElement | null>(null);
let observer: IntersectionObserver | undefined;
onMounted(() => {
  if (f.ai) return settle(f.ai);
  // Half a screen early, so the answer is often there by the time the card is.
  observer = new IntersectionObserver(
    (entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      observer?.disconnect();
      api
        .post<Explanation>("/api/explain", { quotes: first.map(place) })
        .then(settle, (err) => settle({ error: errorText(err) }));
    },
    { root: props.observeRoot, rootMargin: "50% 0px" },
  );
  observer.observe(card.value!);
});
onBeforeUnmount(() => observer?.disconnect());

// Quotes the AI did not cover (beyond the first SHOWN, or all if it failed), in one call.
async function translateQuotes() {
  const todo = pool.value.filter((p) => !english[p.lang] && (settled.value || !first.includes(p)));
  if (!todo.length || translating.value) return;
  translating.value = true;
  let ok = false;
  try {
    const t = await api.post<Record<string, string>>("/api/translate", { quotes: todo.map(place) });
    for (const p of todo)
      english[p.lang] = { quote: t[p.lang] ?? p.sentence, heading: t[`${p.lang}-heading`] ?? p.heading };
    translateError.value = "";
    ok = true;
  } catch (err) {
    translateError.value = `Could not translate: ${errorText(err)}`;
  }
  translating.value = false;
  // Quotes shown meanwhile. Not after a failure: the same quotes would be sent again at once, forever.
  if (ok) translateQuotes();
}
watch([pool, settled], translateQuotes, { immediate: true });

// Paragraphs in English: the passages translated, the quote marked in them. A finding marked irrelevant
// shows its paragraphs in the original: not worth a translation.
async function translatePassages() {
  if (!context.value || dismissed.value || passagesBusy.value) return;
  const todo = pool.value.filter((p) => inEnglish(p) && !(p.lang in passages));
  if (!todo.length) return;
  passagesBusy.value = true;
  try {
    const t = await api.post<Record<string, string>>("/api/translate", { quotes: todo.map(place), paragraphs: true });
    for (const p of todo) passages[p.lang] = t[p.lang] ?? withMarks(p.text, [p.sentence]);
    passagesError.value = "";
  } catch (err) {
    passagesError.value = `Could not translate the paragraphs: ${errorText(err)}`;
  }
  passagesBusy.value = false;
}
watch(
  () => [
    context.value,
    pool.value
      .filter(inEnglish)
      .map((p) => p.lang)
      .join(),
  ],
  translatePassages,
);

const doLocate = () => {
  notFound.value = !(own && props.locate?.(own));
};
// The whole card shows the page's quote too; its links, buttons, menus and highlights keep their own action.
const onCardClick = (e: MouseEvent) => {
  if (props.locate && own && !(e.target as Element).closest("a, button, mark, .tip, .cdx-popover")) doLocate();
};
const swapQuote = (p: Member) => {
  if (!original.delete(p.lang)) original.add(p.lang);
};
</script>

<template>
  <Teleport defer :to="irrelevantTarget" :disabled="!dismissed || !irrelevantTarget">
    <article ref="card" class="card" :class="{ locatable: locate && own }" @click="onCardClick">
      <div class="meta">
        <CdxInfoChip v-if="ai && !ai.discrepancy" :status="KIND_STATUS.none">Irrelevant</CdxInfoChip>
        <CdxInfoChip v-else-if="ai?.kind" :status="KIND_STATUS[ai.kind]">{{ KIND_NAMES[ai.kind] }}</CdxInfoChip>
        <span class="score">
          <template v-if="f.outlier">Outlier: {{ langName(f.lang) }}</template>
          <NumbersButton :finding="f" />
        </span>
      </div>
      <h3 v-if="!settled" class="pending">
        <CdxProgressIndicator>Asking the AI</CdxProgressIndicator> Asking the AI how they differ…
      </h3>
      <h3 v-else-if="ai?.title">{{ ai.title }}</h3>
      <CdxMessage v-if="aiError" type="warning" inline>{{ aiError }}</CdxMessage>
      <p v-if="ai && !ai.discrepancy" class="reason">
        Marked irrelevant by the AI check: these passages neither disagree on facts nor differ clearly in tone or
        framing. Their distance on the axis comes from other differences, such as what they include, their length or
        detail.
      </p>
      <p v-if="ai?.description" class="summary"><MarkedText :parts="description" @hover="hovered = $event" /></p>

      <div class="quotes">
        <div
          v-for="p in pool"
          :key="p.lang"
          class="quote"
          :class="[
            `c${members.indexOf(p) % 4}`,
            { here: p.lang === focusLang, outlier: outliers.includes(p.lang), linked: hovered === p.lang },
          ]"
        >
          <h4>
            <b>{{ langName(p.lang) }}<template v-if="p.lang === focusLang"> · this page</template></b>
            <span class="muted">§ {{ (inEnglish(p) ? english[p.lang].heading : p.heading) || "(intro)" }}</span>
            <a
              v-if="p.lang !== focusLang"
              :href="snippetUrl(p)"
              target="_blank"
              rel="noopener"
              :title="`Open this quote on Wikipedia: ${p.title}`"
              :aria-label="`Open this quote on ${langName(p.lang)} Wikipedia`"
            >
              <CdxIcon :icon="cdxIconLinkExternal" size="small" />
            </a>
          </h4>

          <blockquote v-if="context && inEnglish(p) && !dismissed">
            <span v-if="passages[p.lang]" class="quoted"><MarkedText :text="passages[p.lang]" /></span>
            <span v-else-if="passagesError" class="error">{{ passagesError }}</span>
            <span v-else class="pending"
              ><CdxProgressIndicator>Translating</CdxProgressIndicator> Translating the paragraphs…</span
            >
          </blockquote>
          <ExpandableQuote
            v-else-if="context"
            :member="p"
            :ctx="ctx[p.lang]"
            :quote="withMarks(p.text, [p.sentence])"
          />
          <blockquote v-else>
            <span class="quoted"
              ><MarkedText :text="inEnglish(p) ? english[p.lang].quote : withMarks(p.sentence, phrases[p.lang])"
            /></span>
          </blockquote>

          <div class="foot">
            <CdxButton v-if="locate && p.lang === focusLang" size="small" :title="locateLabel.title" @click="doLocate">
              <CdxIcon :icon="cdxIconSearch" size="small" />
              {{ notFound ? "Not found on this page" : locateLabel.text }}
            </CdxButton>
            <template v-if="p.lang !== 'en'">
              <span v-if="english[p.lang]" class="tr">
                <CdxButton
                  size="small"
                  weight="quiet"
                  :action="inEnglish(p) ? 'default' : 'progressive'"
                  :aria-pressed="String(!inEnglish(p))"
                  :aria-label="
                    inEnglish(p) ? `Show the original ${langName(p.lang)} quote` : 'Show the English translation'
                  "
                  @click="swapQuote(p)"
                >
                  <CdxIcon :icon="cdxIconLanguage" size="small" />
                </CdxButton>
                <div class="tip" role="tooltip">
                  <div class="section">
                    {{ inEnglish(p) ? `Original (${langName(p.lang)})` : "English translation" }}
                  </div>
                  <MarkedText :text="inEnglish(p) ? withMarks(p.sentence, phrases[p.lang]) : english[p.lang].quote" />
                </div>
              </span>
              <span v-else-if="!settled || translating" class="tr" title="Translating…"
                ><CdxProgressIndicator>Translating</CdxProgressIndicator></span
              >
            </template>
          </div>
        </div>
        <CdxMessage v-if="translateError" type="error" inline>{{ translateError }}</CdxMessage>
      </div>

      <div class="tools">
        <CdxButton v-if="members.length > SHOWN" size="small" @click="all = !all">
          <CdxIcon :icon="cdxIconListBullet" size="small" />
          {{ all ? "Show fewer" : `Show all ${members.length} editions` }}
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
