<!-- A finding, the same in the web app and the extension. Its kind comes with it (the decision model's,
     /api/diff); its AI explanation of the first SHOWN quotes is asked for once the card nears the view
     (/api/explain, by the quotes' place): title, a description quoting the differing words, and each
     quote in English with those words marked; the original keeps the same words marked. Quotes show
     in English; each one's translate button shows the original on hover and swaps to it on click. Quotes
     beyond the first SHOWN (all of them if the AI failed), and paragraphs, are translated when shown, by
     their place: the server reads their text. A factual disagreement can ask what the other editions say
     about its subject (/api/consensus): their positions, most editions first. -->
<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
  CdxButton,
  CdxIcon,
  CdxInfoChip,
  CdxMessage,
  CdxProgressIndicator,
  CdxTooltip as vTooltip,
} from "@wikimedia/codex";
import {
  cdxIconArticle,
  cdxIconCollapse,
  cdxIconExpand,
  cdxIconLanguage,
  cdxIconLinkExternal,
  cdxIconListBullet,
  cdxIconSearch,
  cdxIconUserGroup,
} from "@wikimedia/codex-icons";
import MarkedText from "./MarkedText";
import ExpandableQuote, { contextOf } from "./ExpandableQuote";
import NumbersButton from "./NumbersButton.vue";
import { API, errorText, type Consensus, type English, type Explanation, type Finding, type Member } from "./types";
import { KIND_NAMES, KIND_STATUS, SHOWN, langName, linkMarks, markParts, snippetUrl, withMarks } from "./util";

const props = withDefaults(
  defineProps<{
    finding: Finding;
    focusLang?: string | null; // the extension's page edition: its quote first
    observeRoot?: HTMLElement | null; // the scrolling element, for a card the AI explains when near view
    paragraphs?: boolean; // the web app's "Show paragraphs", with expanding context
    locate?: ((m: Member) => boolean) | null; // extension: show the page edition's quote on the page
    locateLabel?: { text: string; title: string };
  }>(),
  {
    focusLang: null,
    observeRoot: null,
    paragraphs: false,
    locate: null,
    locateLabel: () => ({ text: "Show on page", title: "Highlight this on the page" }),
  },
);
const api = inject(API)!;

const f = props.finding;
const outliers = f.outlier ? [f.lang] : [];
// In the API's order (the page's edition first, then the outlier); a card shows the first SHOWN unless expanded.
const members = f.members;
const first = members.slice(0, SHOWN);
const own = members.find((m) => m.lang === props.focusLang);

// The AI's explanation, asked for once the card nears the view: only findings someone reads cost an LLM
// call. If it failed, the quotes stay in their language until translated.
const ai = ref<Explanation | null>(null),
  aiError = ref(""),
  settled = ref(false);
const english = reactive<English>({}),
  phrases = reactive<Record<string, string[]>>({}),
  original = reactive(new Set<string>());
const all = ref(false),
  context = ref(false),
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
  }
  settled.value = true;
}
const card = ref<HTMLElement | null>(null);
let observer: IntersectionObserver | undefined;
onMounted(() => {
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

// Paragraphs in English: the passages translated, the quote marked in them.
async function translatePassages() {
  if (!context.value || passagesBusy.value) return;
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
  if (props.locate && own && !(e.target as Element).closest("a, button, mark, .tip, .cdx-popover, .consensus"))
    doLocate();
};
const swapQuote = (p: Member) => {
  if (!original.delete(p.lang)) original.add(p.lang);
};

// What the other editions say about a factual disagreement's subject: asked for once, when first opened.
const others = ref(false),
  consensus = ref<Consensus | null>(null),
  consensusError = ref("");
async function toggleOthers() {
  others.value = !others.value;
  if (!others.value || consensus.value || !ai.value) return;
  consensusError.value = "";
  try {
    consensus.value = await api.post<Consensus>("/api/consensus", {
      quotes: first.map(place),
      subject: ai.value.subject,
    });
  } catch (err) {
    consensusError.value = `Could not ask the other editions: ${errorText(err)}`;
  }
}
const stated = computed(() => (consensus.value ? Object.keys(consensus.value.sentences).length : 0));
// A position holding a shown quote takes that quote's colour.
const colorOf = (langs: string[]) => {
  const i = first.findIndex((m) => langs.includes(m.lang));
  return i < 0 ? "" : `c${i % 4}`;
};
const leads = computed(() => {
  const p = consensus.value?.positions ?? [];
  return p.length > 1 && p[0].editions.length > p[1].editions.length;
});
const TOP = 5; // positions listed before "Show all", besides those of the quotes
const allPositions = ref(false);
const positions = computed(() =>
  (consensus.value?.positions ?? [])
    .map((p, i) => ({ ...p, i, color: colorOf(p.editions) }))
    .filter((p) => allPositions.value || p.i < TOP || p.color),
);
const hiddenPositions = computed(() => (consensus.value?.positions.length ?? 0) - positions.value.length);
</script>

<template>
  <article ref="card" class="card" :class="{ locatable: locate && own }" @click="onCardClick">
    <div class="meta">
      <CdxInfoChip v-if="f.kind" :status="KIND_STATUS[f.kind]">{{ KIND_NAMES[f.kind] }}</CdxInfoChip>
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

        <blockquote v-if="context && inEnglish(p)">
          <span v-if="passages[p.lang]" class="quoted"><MarkedText :text="passages[p.lang]" /></span>
          <span v-else-if="passagesError" class="error">{{ passagesError }}</span>
          <span v-else class="pending"
            ><CdxProgressIndicator>Translating</CdxProgressIndicator> Translating the paragraphs…</span
          >
        </blockquote>
        <ExpandableQuote v-else-if="context" :member="p" :ctx="ctx[p.lang]" :quote="withMarks(p.text, [p.sentence])" />
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
            <span v-else-if="!settled || translating" class="tr"
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
      <CdxButton
        v-if="f.kind === 'factual' && ai?.subject"
        size="small"
        :aria-expanded="String(others)"
        @click="toggleOthers"
      >
        <CdxIcon :icon="cdxIconUserGroup" size="small" /> What do the other editions say?
        <CdxIcon :icon="others ? cdxIconCollapse : cdxIconExpand" size="small" />
      </CdxButton>
    </div>
    <section v-if="others" class="consensus">
      <CdxMessage v-if="consensusError" type="error" inline>{{ consensusError }}</CdxMessage>
      <p v-else-if="!consensus" class="pending">
        <CdxProgressIndicator>Asking</CdxProgressIndicator> Reading the other editions…
      </p>
      <p v-else-if="!consensus.positions.length" class="muted">
        No other edition has a sentence close enough to these quotes to compare.
      </p>
      <template v-else>
        <p class="muted">
          {{ stated }} of the {{ consensus.asked }} other editions closest to these quotes state {{ ai?.subject }}:
        </p>
        <ol>
          <li v-for="p in positions" :key="p.i" :class="p.color">
            <b>{{ p.claim }}</b>
            <span class="muted"> · {{ p.editions.length }} edition{{ p.editions.length === 1 ? "" : "s" }}</span>
            <CdxInfoChip v-if="p.i === 0 && leads" class="lead">Most editions</CdxInfoChip>
            <div class="langs">
              <span
                v-for="l in p.editions"
                :key="l"
                v-tooltip="consensus.sentences[l] ?? 'One of the quotes above'"
                tabindex="0"
                >{{ langName(l) }}</span
              >
            </div>
          </li>
        </ol>
        <CdxButton
          v-if="hiddenPositions || allPositions"
          size="small"
          weight="quiet"
          @click="allPositions = !allPositions"
        >
          {{ allPositions ? "Show fewer" : `Show ${hiddenPositions} more` }}
        </CdxButton>
        <p class="muted">
          Most editions is not proof: they may give the value for different dates, or copy one another. Hover or focus
          an edition for its sentence.
        </p>
      </template>
    </section>
  </article>
</template>
