<!-- The web app: search a topic, see where its Wikipedia editions state things differently, a page of
     findings at a time. The query lives in the URL (?title=…&lang=…&page=…&langs=fi,sv&dialects=1&kinds=factual),
     so results can be shared and Back/Forward work; `lang` (the edition the title is from) comes from a
     suggestion or the extension's link. -->
<script setup lang="ts">
import { computed, inject, nextTick, ref } from "vue";
import {
  CdxAccordion,
  CdxButton,
  CdxIcon,
  CdxMessage,
  CdxTypeaheadSearch,
  type SearchResult,
  type SearchResultClickEvent,
} from "@wikimedia/codex";
import { cdxIconNext, cdxIconPrevious } from "@wikimedia/codex-icons";
import FindingCard from "../shared/FindingCard.vue";
import LanguageFilter from "../shared/LanguageFilter.vue";
import LoadingSteps from "../shared/LoadingSteps.vue";
import WikiCrossLogo from "../shared/WikiCrossLogo.vue";
import {
  API,
  errorText,
  statusOf,
  type Diff,
  type Filters,
  type Kind,
  type Limits,
  type Params,
  type TitleSuggestion,
} from "../shared/types";
import { KIND_NAMES, langName } from "../shared/util";
import AboutPage from "./AboutPage.vue";
import EditionsMenu from "./EditionsMenu.vue";

const api = inject(API)!;
const PER_PAGE = 10;

interface Query extends Filters {
  title: string;
  lang?: string | null;
  page: number;
}
const urlQuery = (): Query => {
  const p = new URLSearchParams(location.search);
  return {
    title: p.get("title")?.trim() ?? "",
    lang: p.get("lang"),
    page: Math.max(1, parseInt(p.get("page") ?? "", 10) || 1),
    langs: p.get("langs")?.split(",").filter(Boolean) || null,
    dialects: p.get("dialects") === "1", // hidden unless asked for
    kinds:
      p
        .get("kinds")
        ?.split(",")
        .filter((k): k is Kind => k in KIND_NAMES) || null,
  };
};
// Only the parameters that differ from the defaults.
const params = ({ lang, langs, dialects, kinds }: Query): Params => ({
  ...(lang && { lang }),
  ...(langs && { langs: langs.join(",") }),
  ...(dialects && { dialects: 1 }),
  ...(kinds?.length && { kinds: kinds.join(",") }),
});
const queryString = (q: Query) =>
  `${new URLSearchParams({ title: q.title, ...params(q), ...(q.page > 1 && { page: String(q.page) }) } as Record<string, string>)}`;

// --- The search field: Codex's TypeaheadSearch, Wikipedia's own search box. Suggestions come from
// /api/titles, one per topic, with thumbnail and description. Picking one compares it in its edition;
// typed text is compared as a title from any edition (unless it is exactly a suggestion's title).
type Suggestion = SearchResult & { lang: string };
const searchValue = ref(""),
  searchKey = ref(0),
  suggestions = ref<Suggestion[]>([]),
  searchBox = ref<HTMLElement | null>(null);
let programmatic: string | null = null; // the title put into the field by a search, not typed: no suggestions for it
const setSearchValue = (title: string) => {
  if (title === searchValue.value) return;
  programmatic = searchValue.value = title;
  searchKey.value++; // TypeaheadSearch takes its text only when mounted
};
const typedValue = () => searchBox.value?.querySelector("input")?.value.trim() || "";
async function onInput(typed: string) {
  typed = typed.trim();
  if (typed === programmatic) {
    programmatic = null;
    return;
  }
  if (typed.length < 2) {
    suggestions.value = [];
    return;
  }
  let items: TitleSuggestion[];
  try {
    items = await api.get<TitleSuggestion[]>("/api/titles", { q: typed });
  } catch {
    return;
  }
  if (typedValue() !== typed || !Array.isArray(items)) return; // typed on
  suggestions.value = items.map((s) => ({
    value: `${s.lang}:${s.title}`,
    label: s.title,
    description: s.description || "",
    lang: s.lang,
    supportingText: s.lang !== "en" ? `(${langName(s.lang)})` : "",
    thumbnail: s.thumbnail && /^https:\/\//.test(s.thumbnail) ? { url: s.thumbnail } : null,
    url: `?${queryString({ ...urlQuery(), title: s.title, lang: s.lang, page: 1, langs: null })}`,
  }));
}
const choose = (title: string, lang?: string) => {
  const q: Query = { ...urlQuery(), title, lang, page: 1, langs: null };
  if (q.title) search(q, queryString(q) !== location.search.slice(1));
};
// A suggestion is a link (for a new tab); a plain click compares it here, without a page load.
const onSearchClick = (e: MouseEvent) => {
  if (!e.ctrlKey && !e.metaKey && !e.shiftKey && (e.target as Element).closest("a")) e.preventDefault();
};
const onResultClick = ({ searchResult }: SearchResultClickEvent) => {
  if (searchResult) choose(searchResult.label ?? "", (searchResult as Suggestion).lang);
};
// Codex would load the form's action (or a picked suggestion's URL): compare here instead.
async function onSearchSubmit(e: Event) {
  e.preventDefault();
  e.stopPropagation();
  await nextTick();
  const typed = typedValue(),
    match = suggestions.value.find((s) => s.label === typed);
  choose(typed, match?.lang);
}

// --- Results.
// The loading view lists a search's steps until /api/diff answers; then the results show.
interface Run {
  title: string;
  id: number;
}
type View =
  | { state: "idle" }
  | { state: "error"; message: string }
  | ({ state: "loading" } & Run)
  | ({ state: "done"; data: Diff; query: Query } & Run);
const view = ref<View>({ state: "idle" });
// /about shows the About page instead of a search (the server serves the app there too).
const about = ref(location.pathname === "/about");
let current = 0;
async function search(q: Query, push: boolean) {
  about.value = false;
  if (push) history.pushState(null, "", `/?${queryString(q)}`);
  setSearchValue(q.title);
  document.title = `${q.title} — WikiCross`;
  const mine = ++current; // a slower, older search must not overwrite a newer one
  view.value = { state: "loading", title: q.title, id: mine };
  try {
    // Unexplained: each card asks the AI as it nears the view, so only findings someone reads cost a call.
    const data = await api.get<Diff>("/api/diff", {
      title: q.title,
      limit: PER_PAGE,
      offset: (q.page - 1) * PER_PAGE,
      ...params(q),
    });
    if (mine !== current) return;
    view.value = { state: "done", data, query: q, title: q.title, id: mine };
  } catch (err) {
    if (mine === current)
      view.value = {
        state: "error",
        message: statusOf(err) ? errorText(err) : `WikiCross server not reachable: ${errorText(err)}`,
      };
  }
}
const done = computed(() => (view.value.state === "done" ? view.value : null));
window.addEventListener("popstate", () => {
  about.value = location.pathname === "/about";
  const q = urlQuery();
  if (!about.value && q.title) search(q, false);
});
if (!about.value && urlQuery().title) search(urlQuery(), false);
// The rate limits, if on (RATE_LIMIT in app.py): stated on the home page.
const limits = ref<Limits | null>(null);
api
  .get<Limits | null>("/api/limits")
  .then((l) => {
    limits.value = l;
  })
  .catch(() => {});

const head = computed(
  () => done.value && (done.value.data.articles.find((a) => a.lang === "en") || done.value.data.articles[0]),
);
const pages = computed(() => Math.ceil((done.value?.data.total ?? 0) / PER_PAGE));
const go = (page: number) => {
  if (done.value) search({ ...done.value.query, page }, true);
  window.scrollTo(0, 0);
};
const refilter = (filters: Filters) => {
  if (done.value) search({ ...done.value.query, ...filters, page: 1 }, true);
};
</script>

<template>
  <header>
    <a class="wordmark" href="/" title="WikiCross home"><WikiCrossLogo />WikiCross</a>
    <div ref="searchBox" role="search" @click.capture="onSearchClick" @submit.capture="onSearchSubmit">
      <CdxTypeaheadSearch
        id="q"
        :key="searchKey"
        form-action="/"
        :search-results="suggestions"
        :initial-input-value="searchValue"
        placeholder="Search an article: Talvisota, Winter War, Stepan Bandera…"
        search-results-label="Suggested articles"
        use-button
        button-label="Compare"
        highlight-query
        show-thumbnail
        @input="onInput"
        @search-result-click="onResultClick"
      />
    </div>
  </header>
  <main>
    <AboutPage v-if="about" />
    <template v-else>
      <template v-if="view.state === 'idle'">
        <p class="muted">Pick an article to see where all its Wikipedia versions frame things differently.</p>
        <CdxMessage v-if="limits" type="warning">
          Fair use: outside the event network, each address can make {{ limits.api }} requests a minute, and
          {{ limits.llm }} a minute for AI summaries and translations. Past that, wait a minute and try again.
        </CdxMessage>
      </template>

      <CdxMessage v-else-if="view.state === 'error'" type="error">{{ view.message }}</CdxMessage>

      <LoadingSteps v-if="view.state === 'loading'" :key="view.id" :title="view.title" />

      <div v-if="done" :key="done.id" class="layout">
        <LanguageFilter
          :languages="done.data.languages"
          :counts="done.data.kinds"
          :langs="done.query.langs"
          :dialects="done.query.dialects"
          :kinds="done.query.kinds"
          @change="refilter"
        />
        <div class="results">
          <div class="pagehead">
            <h1>{{ head?.title }}</h1>
            <EditionsMenu :articles="done.data.articles" />
          </div>
          <CdxMessage v-if="done.data.unchecked" type="warning" inline>
            Some findings could not be checked, so they are shown unfiltered and without a kind:
            {{ done.data.unchecked }}
          </CdxMessage>
          <template v-if="done.data.total">
            <div class="listhead">
              <h2>{{ done.data.total }} differences</h2>
              <nav v-if="pages > 1" class="pager compact" aria-label="Pages of differences">
                <CdxButton
                  weight="quiet"
                  :disabled="done.query.page <= 1"
                  aria-label="Previous page"
                  @click="go(done.query.page - 1)"
                  ><CdxIcon :icon="cdxIconPrevious"
                /></CdxButton>
                <span>{{ done.query.page }} / {{ pages }}</span>
                <CdxButton
                  weight="quiet"
                  :disabled="done.query.page >= pages"
                  aria-label="Next page"
                  @click="go(done.query.page + 1)"
                  ><CdxIcon :icon="cdxIconNext"
                /></CdxButton>
              </nav>
            </div>
            <FindingCard v-for="(f, i) in done.data.differences" :key="`${done.id}-${i}`" :finding="f" paragraphs />
            <nav v-if="pages > 1" class="pager" aria-label="Pages of differences">
              <CdxButton :disabled="done.query.page <= 1" @click="go(done.query.page - 1)"
                ><CdxIcon :icon="cdxIconPrevious" /> Previous</CdxButton
              >
              <span>Page {{ done.query.page }} of {{ pages }}</span>
              <CdxButton :disabled="done.query.page >= pages" @click="go(done.query.page + 1)"
                >Next <CdxIcon :icon="cdxIconNext"
              /></CdxButton>
            </nav>
          </template>
          <p v-else class="muted">The editions state nothing differently that WikiCross can find.</p>
          <CdxAccordion class="timing">
            <template #title>Loaded in {{ Math.round(done.data.progress.seconds) }} s</template>
            <LoadingSteps :title="done.title" :result="done.data.progress" />
          </CdxAccordion>
        </div>
      </div>
    </template>
  </main>
  <footer>
    <a href="/about">About WikiCross</a>
    <span
      >Quotes from Wikipedia, under
      <a href="https://creativecommons.org/licenses/by-sa/4.0/" rel="license">CC BY-SA 4.0</a></span
    >
    <span>Not affiliated with the Wikimedia Foundation</span>
    <a href="https://github.com/ardubev16/junction2026">Source code</a>
  </footer>
</template>
