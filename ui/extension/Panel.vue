<!-- The extension's button and panel on a Wikipedia article: what this edition states differently from
     the others (up to 30 findings, this edition's first), then the rest in an accordion. Cards ask the AI
     as they scroll into view, and "Show on page" / "Find in source" shows the evidence (the page is the
     context: no "Show paragraphs"). The logo opens the topic in the web app. Filters are kept for this
     page view only. -->
<script setup>
import { computed, inject, ref } from "vue";
import { CdxAccordion, CdxButton, CdxIcon, CdxMessage, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconAlert, cdxIconClose, cdxIconEye, cdxIconEyeClosed } from "@wikimedia/codex-icons";
import FindingCard from "../shared/FindingCard.vue";
import LanguageFilter from "../shared/LanguageFilter.vue";
import Logo from "../shared/Logo.vue";
import { langName } from "../shared/util.js";

const props = defineProps({
  title: String, lang: String, editing: Boolean,
  locate: Function, locateLabel: Function, openHome: Function, remove: Function,
});
const api = inject("api");

const open = ref(false), panel = ref(null), irrelevant = ref(null);
const view = ref({ state: "idle" });  // idle | loading | error | done
const stage = ref(""), seconds = ref("");
let query = { langs: null, dialects: true }, requested = false, loads = 0;
const dismissed = ref(0), showIrrelevant = ref(false);

function load(next = query) {
  requested = true;
  query = next;
  const mine = ++loads;
  view.value = { state: "loading" };
  stage.value = "Looking the topic up…";
  seconds.value = "";
  // The server's current stage, polled each second while it works.
  const poll = setInterval(() => api.get("/api/progress", { title: props.title }).then((p) => {
    if (!p.stage || mine !== loads) return;
    stage.value = `${p.stage}…`;
    seconds.value = `${p.seconds} s`;
  }).catch(() => {}), 1000);
  const filtered = { ...(query.langs && { langs: query.langs.join(",") }), ...(!query.dialects && { dialects: false }) };
  api.get("/api/diff", { title: props.title, lang: props.lang, focus: props.lang, limit: 30, ...filtered })
    .then((data) => {
      if (mine !== loads) return;
      dismissed.value = 0;
      showIrrelevant.value = false;
      view.value = { state: "done", data, id: mine };
    })
    .catch((err) => {
      if (mine !== loads) return;
      // No other edition: stay out of the way (but a filter leaving too few is the reader's to undo).
      if (!props.editing && err.status === 404 && !Object.keys(filtered).length) return props.remove();
      view.value = { state: "error", message: err.message, status: err.status };
    })
    .finally(() => clearInterval(poll));
}
const toggle = () => {
  open.value = !open.value;
  if (!requested) load();
};
// In the edit views at once; in the article view only when asked, so that reading Wikipedia does not
// embed every article visited.
if (props.editing) load();

const data = computed(() => view.value.data);
const mine = computed(() => data.value.differences.filter((f) => f.members.some((m) => m.lang === props.lang)));
const elsewhere = computed(() => data.value.differences.filter((f) => !mine.value.includes(f)));
const filtered = computed(() => !!query.langs || !query.dialects);
const label = computed(() => {
  if (view.value.state === "done") return `WikiCross · ${mine.value.length}`;
  if (view.value.state === "error") return view.value.status ? "WikiCross · –" : "WikiCross · ?";
  return "WikiCross";
});
const card = (f) => ({ finding: f, focusLang: props.lang, lazy: true, observeRoot: panel.value, locate: props.locate,
                       locateLabel: props.locateLabel(), irrelevantTarget: irrelevant.value, onDismiss: () => dismissed.value++ });
</script>

<template>
  <CdxButton class="toggle" :action="view.state === 'done' && mine.length ? 'progressive' : 'default'"
             :weight="view.state === 'done' && mine.length ? 'primary' : 'normal'" @click="toggle">
    <CdxProgressIndicator v-if="view.state === 'loading'">Comparing the editions</CdxProgressIndicator>
    <CdxIcon v-else-if="view.state === 'done' && mine.length" :icon="cdxIconAlert" size="small" />
    {{ label }}
  </CdxButton>
  <section v-show="open" ref="panel" class="panel">
    <header>
      <h2><button class="home" type="button" title="Open this topic in the WikiCross web app" @click="openHome"><Logo />WikiCross</button></h2>
      <CdxButton weight="quiet" aria-label="Close" title="Close" @click="open = false"><CdxIcon :icon="cdxIconClose" /></CdxButton>
    </header>
    <div class="body">
      <div v-if="view.state === 'loading'" class="loading">
        <CdxProgressIndicator>Comparing the editions</CdxProgressIndicator>
        <div>
          <div role="status">{{ stage }} <span class="muted" aria-hidden="true">{{ seconds }}</span></div>
          <p class="muted">The first time an article is asked for, all its Wikipedia versions are fetched and embedded: this can take a few minutes.</p>
        </div>
      </div>
      <template v-else-if="view.state === 'error'">
        <CdxMessage type="error">{{ view.message }}</CdxMessage>
        <CdxButton v-if="filtered" size="small" @click="load({ langs: null, dialects: true })">Compare all editions</CdxButton>
      </template>
      <template v-else-if="view.state === 'done'" :key="view.id">
        <LanguageFilter :languages="data.languages" :langs="query.langs" :dialects="query.dialects" @change="load" />
        <CdxMessage v-if="!data.languages.includes(lang)" inline>
          This version ({{ langName(lang) }}) is not compared: its script is not supported yet. Below, what the others state differently.
        </CdxMessage>
        <CdxMessage v-else-if="!data.articles.some((a) => a.lang === lang)" inline>
          This version ({{ langName(lang) }}) is left out by the filters. Below, what the others state differently.
        </CdxMessage>
        <CdxMessage v-else-if="!mine.length" inline>Nothing in this edition is framed differently from the other editions.</CdxMessage>
        <FindingCard v-for="(f, i) in mine" :key="`${view.id}-m${i}`" v-bind="card(f)" />
        <CdxAccordion v-if="elsewhere.length" separation="none" class="elsewhere">
          <template #title>{{ elsewhere.length }} more between the other editions</template>
          <FindingCard v-for="(f, i) in elsewhere" :key="`${view.id}-e${i}`" v-bind="card(f)" />
        </CdxAccordion>
        <CdxButton v-if="dismissed" size="small" :aria-expanded="String(showIrrelevant)" @click="showIrrelevant = !showIrrelevant">
          <CdxIcon :icon="showIrrelevant ? cdxIconEyeClosed : cdxIconEye" size="small" />
          {{ showIrrelevant ? "Hide" : "Show" }} {{ dismissed }} finding{{ dismissed === 1 ? "" : "s" }} the AI marked as irrelevant
        </CdxButton>
        <div v-show="showIrrelevant" ref="irrelevant" class="irrelevant"></div>
      </template>
    </div>
  </section>
</template>
