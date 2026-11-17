<!-- The web app: search a topic, see where its Wikipedia editions state things differently, a page of
     findings at a time. The query lives in the URL (?title=…&lang=…&page=…&langs=fi,sv&dialects=0), so
     results can be shared and Back/Forward work; `lang` (the edition the title is from) comes from a
     suggestion or the extension's link. -->
<script setup>
import { computed, inject, nextTick, ref } from "vue";
import { CdxButton, CdxIcon, CdxMessage, CdxTypeaheadSearch } from "@wikimedia/codex";
import { cdxIconEye, cdxIconEyeClosed, cdxIconNext, cdxIconPrevious } from "@wikimedia/codex-icons";
import FindingCard from "../shared/FindingCard.vue";
import LanguageFilter from "../shared/LanguageFilter.vue";
import LoadingSteps from "../shared/LoadingSteps.vue";
import Logo from "../shared/Logo.vue";
import { langName } from "../shared/util.js";
import EditionsMenu from "./EditionsMenu.vue";

const api = inject("api");
const PER_PAGE = 10;

const urlQuery = () => {
  const p = new URLSearchParams(location.search);
  return { title: p.get("title")?.trim(), lang: p.get("lang"), page: Math.max(1, parseInt(p.get("page"), 10) || 1),
           langs: p.get("langs")?.split(",").filter(Boolean) || null, dialects: p.get("dialects") !== "0" };
};
// Only the parameters that differ from the defaults.
const params = ({ lang, langs, dialects }) => ({ ...(lang && { lang }), ...(langs && { langs: langs.join(",") }), ...(!dialects && { dialects: 0 }) });
const queryString = (q) => `${new URLSearchParams({ title: q.title, ...params(q), ...(q.page > 1 && { page: q.page }) })}`;

// --- The search field: Codex's TypeaheadSearch, Wikipedia's own search box. Suggestions come from
// /api/titles, one per topic, with thumbnail and description. Picking one compares it in its edition;
// typed text is compared as a title from any edition (unless it is exactly a suggestion's title).
const searchValue = ref(""), searchKey = ref(0), suggestions = ref([]), searchBox = ref(null);
let programmatic = null;  // the title put into the field by a search, not typed: no suggestions for it
const setSearchValue = (title) => {
  if (title === searchValue.value) return;
  programmatic = searchValue.value = title;
  searchKey.value++;  // TypeaheadSearch takes its text only when mounted
};
const typedValue = () => searchBox.value?.querySelector("input")?.value.trim() || "";
async function onInput(typed) {
  typed = typed.trim();
  if (typed === programmatic) { programmatic = null; return; }
  if (typed.length < 2) { suggestions.value = []; return; }
  let items;
  try { items = await api.get("/api/titles", { q: typed }); } catch { return; }
  if (typedValue() !== typed || !Array.isArray(items)) return;  // typed on
  suggestions.value = items.map((s) => ({
    value: `${s.lang}:${s.title}`, label: s.title, description: s.description || "", lang: s.lang,
    supportingText: s.lang !== "en" ? `(${langName(s.lang)})` : "",
    thumbnail: /^https:\/\//.test(s.thumbnail || "") ? { url: s.thumbnail } : null,
    url: `?${queryString({ title: s.title, lang: s.lang, page: 1, dialects: urlQuery().dialects })}`,
  }));
}
const choose = (title, lang) => {
  const q = { title, ...(lang && { lang }), page: 1, dialects: urlQuery().dialects };
  if (q.title) search(q, queryString(q) !== location.search.slice(1));
};
// A suggestion is a link (for a new tab); a plain click compares it here, without a page load.
const onSearchClick = (e) => { if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.target.closest("a")) e.preventDefault(); };
const onResultClick = ({ searchResult }) => { if (searchResult) choose(searchResult.label, searchResult.lang); };
// Codex would load the form's action (or a picked suggestion's URL): compare here instead.
async function onSearchSubmit(e) {
  e.preventDefault();
  e.stopPropagation();
  await nextTick();
  const typed = typedValue(), match = suggestions.value.find((s) => s.label === typed);
  choose(typed, match?.lang);
}

// --- Results.
// Findings the AI check does not confirm leave the list for a hidden one under it, behind a button.
const irrelevant = ref(null), dismissed = ref(0), showIrrelevant = ref(false);
const resetDismissed = () => { dismissed.value = 0; showIrrelevant.value = false; };
const view = ref({ state: "idle" });  // idle | loading | error | done
let current = 0;
async function search(q, push) {
  if (push) history.pushState(null, "", `?${queryString(q)}`);
  setSearchValue(q.title);
  document.title = `${q.title} — WikiCross`;
  const mine = ++current;  // a slower, older search must not overwrite a newer one
  view.value = { state: "loading", title: q.title, id: mine };
  try {
    const data = await api.get("/api/diff", { title: q.title, limit: PER_PAGE, offset: (q.page - 1) * PER_PAGE, ...params(q) });
    if (mine === current) { resetDismissed(); view.value = { state: "done", data, query: q, id: mine }; }
  } catch (err) {
    if (mine === current) view.value = { state: "error", message: err.status ? err.message : `WikiCross server not reachable: ${err.message}` };
  }
}
window.addEventListener("popstate", () => { const q = urlQuery(); if (q.title) search(q, false); });
if (urlQuery().title) search(urlQuery(), false);
// The rate limits, if on (RATE_LIMIT in app.py): stated on the home page.
const limits = ref(null);
api.get("/api/limits").then((l) => { limits.value = l; }).catch(() => {});

const data = computed(() => view.value.data);
const query = computed(() => view.value.query);
const head = computed(() => data.value.articles.find((a) => a.lang === "en") || data.value.articles[0]);
const pages = computed(() => Math.ceil(data.value.total / PER_PAGE));
const from = computed(() => (query.value.page - 1) * PER_PAGE);
const go = (page) => { search({ ...query.value, page }, true); window.scrollTo(0, 0); };
const refilter = ({ langs, dialects }) => search({ ...query.value, langs, dialects, page: 1 }, true);

</script>

<template>
  <header>
    <a class="wordmark" href="/" title="WikiCross home"><Logo />WikiCross</a>
    <div ref="searchBox" role="search" @click.capture="onSearchClick" @submit.capture="onSearchSubmit">
      <CdxTypeaheadSearch :key="searchKey" id="q" form-action="/" :search-results="suggestions" :initial-input-value="searchValue"
                          placeholder="Search an article: Talvisota, Winter War, Stepan Bandera…" search-results-label="Suggested articles"
                          use-button button-label="Compare" highlight-query show-thumbnail
                          @input="onInput" @search-result-click="onResultClick" />
    </div>
  </header>
  <main>
    <template v-if="view.state === 'idle'">
      <p class="muted">Pick an article to see where all its Wikipedia versions frame things differently.</p>
      <CdxMessage v-if="limits" type="warning">
        Fair use: outside the event network, each address can make {{ limits.api }} requests a minute, and {{ limits.llm }} a
        minute for AI summaries and translations. Past that, wait a minute and try again.
      </CdxMessage>
    </template>

    <LoadingSteps v-else-if="view.state === 'loading'" :key="view.id" :title="view.title" />

    <CdxMessage v-else-if="view.state === 'error'" type="error">{{ view.message }}</CdxMessage>

    <template v-else :key="view.id">
      <div class="pagehead">
        <h1>{{ head.title }}</h1>
        <EditionsMenu :articles="data.articles" />
      </div>
      <LanguageFilter :languages="data.languages" :langs="query.langs" :dialects="query.dialects" @change="refilter" />
      <template v-if="data.total">
        <h2>{{ data.total }} differences</h2>
        <p class="muted">Strongest first. Showing {{ from + 1 }}–{{ from + data.differences.length }}.</p>
        <FindingCard v-for="(f, i) in data.differences" :key="`${view.id}-${i}`" :finding="f" paragraphs
                     :irrelevant-target="irrelevant" @dismiss="dismissed++" />
        <CdxButton v-if="dismissed" size="small" :aria-expanded="String(showIrrelevant)" @click="showIrrelevant = !showIrrelevant">
          <CdxIcon :icon="showIrrelevant ? cdxIconEyeClosed : cdxIconEye" size="small" />
          {{ showIrrelevant ? "Hide" : "Show" }} {{ dismissed }} finding{{ dismissed === 1 ? "" : "s" }} the AI marked as irrelevant
        </CdxButton>
        <div v-show="showIrrelevant" ref="irrelevant" class="irrelevant"></div>
        <nav v-if="pages > 1" class="pager" aria-label="Pages of differences">
          <CdxButton :disabled="query.page <= 1" @click="go(query.page - 1)"><CdxIcon :icon="cdxIconPrevious" /> Previous</CdxButton>
          <span>Page {{ query.page }} of {{ pages }}</span>
          <CdxButton :disabled="query.page >= pages" @click="go(query.page + 1)">Next <CdxIcon :icon="cdxIconNext" /></CdxButton>
        </nav>
      </template>
      <p v-else class="muted">The editions state nothing differently that WikiCross can find.</p>
    </template>
  </main>
</template>
