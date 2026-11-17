<!-- The extension's button and panel on a Wikipedia article: what this edition states differently from
     the others (up to 30 findings, this edition's first), then the rest in an accordion. Cards ask the AI
     as they near the panel's view, and "Show on page" / "Find in source" shows the evidence (the page is the
     context: no "Show paragraphs"). The logo opens the topic in the web app. Filters are kept for this
     page view only. -->
<script setup lang="ts">
import { computed, inject, ref } from "vue";
import { CdxAccordion, CdxButton, CdxIcon, CdxMessage, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconAlert, cdxIconClose, cdxIconEye, cdxIconEyeClosed } from "@wikimedia/codex-icons";
import FindingCard from "../shared/FindingCard.vue";
import LanguageFilter from "../shared/LanguageFilter.vue";
import LoadingSteps from "../shared/LoadingSteps.vue";
import WikiCrossLogo from "../shared/WikiCrossLogo.vue";
import { API, errorText, statusOf, type Diff, type Filters, type Finding, type Member } from "../shared/types";
import { langName } from "../shared/util";

const props = defineProps<{
  title: string;
  lang: string;
  editing: boolean;
  locate: (m: Member) => boolean;
  locateLabel: () => { text: string; title: string };
  openHome: () => void;
  remove: () => void;
}>();
const api = inject(API)!;

const open = ref(false),
  panel = ref<HTMLElement | null>(null),
  irrelevant = ref<HTMLElement | null>(null);
type View =
  | { state: "idle" }
  | { state: "loading"; id: number }
  | { state: "error"; message: string; status: number }
  | { state: "done"; data: Diff; id: number };
const view = ref<View>({ state: "idle" });
let query: Filters = { langs: null, dialects: true },
  requested = false,
  loads = 0;
const dismissed = ref(0),
  showIrrelevant = ref(false);

function load(next: Filters = query) {
  requested = true;
  query = next;
  const mine = ++loads;
  view.value = { state: "loading", id: mine };
  const filtered = {
    ...(query.langs && { langs: query.langs.join(",") }),
    ...(!query.dialects && { dialects: false }),
  };
  // Unexplained: each card asks the AI as it nears the panel's view, so nothing is asked until the panel opens.
  api
    .get<Diff>("/api/diff", {
      title: props.title,
      lang: props.lang,
      focus: props.lang,
      limit: 30,
      ai: false,
      ...filtered,
    })
    .then((data) => {
      if (mine !== loads) return;
      dismissed.value = 0;
      showIrrelevant.value = false;
      view.value = { state: "done", data, id: mine };
    })
    .catch((err) => {
      if (mine !== loads) return;
      // No other edition: stay out of the way (but a filter leaving too few is the reader's to undo).
      if (!props.editing && statusOf(err) === 404 && !Object.keys(filtered).length) return props.remove();
      view.value = { state: "error", message: errorText(err), status: statusOf(err) };
    });
}
const toggle = () => {
  open.value = !open.value;
  if (!requested) load();
};
// In the edit views at once; in the article view only when asked, so that reading Wikipedia does not
// embed every article visited.
if (props.editing) load();

const data = computed(() => (view.value.state === "done" ? view.value.data : null));
const mine = computed(() => data.value?.differences.filter((f) => f.members.some((m) => m.lang === props.lang)) ?? []);
const elsewhere = computed(() => data.value?.differences.filter((f) => !mine.value.includes(f)) ?? []);
const filtered = computed(() => !!query.langs || !query.dialects);
const label = computed(() => {
  if (view.value.state === "done") return `WikiCross · ${mine.value.length}`;
  if (view.value.state === "error") return view.value.status ? "WikiCross · –" : "WikiCross · ?";
  return "WikiCross";
});
const card = (f: Finding) => ({
  finding: f,
  focusLang: props.lang,
  observeRoot: panel.value,
  locate: props.locate,
  locateLabel: props.locateLabel(),
  irrelevantTarget: irrelevant.value,
  onDismiss: () => dismissed.value++,
});
</script>

<template>
  <CdxButton
    class="toggle"
    :action="view.state === 'done' && mine.length ? 'progressive' : 'default'"
    :weight="view.state === 'done' && mine.length ? 'primary' : 'normal'"
    @click="toggle"
  >
    <CdxProgressIndicator v-if="view.state === 'loading'">Comparing the editions</CdxProgressIndicator>
    <CdxIcon v-else-if="view.state === 'done' && mine.length" :icon="cdxIconAlert" size="small" />
    {{ label }}
  </CdxButton>
  <section v-show="open" ref="panel" class="panel">
    <header>
      <h2>
        <button class="home" type="button" title="Open this topic in the WikiCross web app" @click="openHome">
          <WikiCrossLogo />WikiCross
        </button>
      </h2>
      <CdxButton weight="quiet" aria-label="Close" title="Close" @click="open = false"
        ><CdxIcon :icon="cdxIconClose"
      /></CdxButton>
    </header>
    <div class="body">
      <LoadingSteps v-if="view.state === 'loading'" :key="view.id" :title="title" />
      <template v-else-if="view.state === 'error'">
        <CdxMessage type="error">{{ view.message }}</CdxMessage>
        <CdxButton v-if="filtered" size="small" @click="load({ langs: null, dialects: true })"
          >Compare all editions</CdxButton
        >
      </template>
      <template v-else-if="view.state === 'done'">
        <!-- A new load remounts what keeps state; cards are keyed by load too. -->
        <LanguageFilter
          :key="`filter-${view.id}`"
          :languages="view.data.languages"
          :langs="query.langs"
          :dialects="query.dialects"
          @change="load"
        />
        <CdxMessage v-if="!view.data.languages.includes(lang)" inline>
          This version ({{ langName(lang) }}) is not compared: its script is not supported yet. Below, what the others
          state differently.
        </CdxMessage>
        <CdxMessage v-else-if="!view.data.articles.some((a) => a.lang === lang)" inline>
          This version ({{ langName(lang) }}) is left out by the filters. Below, what the others state differently.
        </CdxMessage>
        <CdxMessage v-else-if="!mine.length" inline
          >Nothing in this edition is framed differently from the other editions.</CdxMessage
        >
        <FindingCard v-for="(f, i) in mine" :key="`${view.id}-m${i}`" v-bind="card(f)" />
        <CdxAccordion v-if="elsewhere.length" :key="`more-${view.id}`" separation="none" class="elsewhere">
          <template #title>{{ elsewhere.length }} more between the other editions</template>
          <FindingCard v-for="(f, i) in elsewhere" :key="`${view.id}-e${i}`" v-bind="card(f)" />
        </CdxAccordion>
        <CdxButton
          v-if="dismissed"
          size="small"
          :aria-expanded="String(showIrrelevant)"
          @click="showIrrelevant = !showIrrelevant"
        >
          <CdxIcon :icon="showIrrelevant ? cdxIconEyeClosed : cdxIconEye" size="small" />
          {{ showIrrelevant ? "Hide" : "Show" }} {{ dismissed }} finding{{ dismissed === 1 ? "" : "s" }} the AI marked
          as irrelevant
        </CdxButton>
        <div v-show="showIrrelevant" :key="`irrelevant-${view.id}`" ref="irrelevant" class="irrelevant"></div>
      </template>
    </div>
  </section>
</template>
