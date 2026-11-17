<!-- The steps of loading a topic, each with its seconds, and the total: the server's (from /api/progress,
     polled each second until `result`, the /api/diff answer's `progress`, has them all), then, in the web
     app, the AI explaining and translating the page's findings (`ai`). Done steps are checked, the current
     one spins with its detail, steps the request did not need are marked so, the rest are to come.
     `times` (performance.now() values: start, result, aiDone) belong to the page, so the list can be shown
     again once loaded. -->
<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref } from "vue";
import { CdxIcon, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconCheck, cdxIconSubtract } from "@wikimedia/codex-icons";
import { API, type AiStep, type Progress, type Times } from "./types";

const props = withDefaults(defineProps<{
  title: string;
  result?: Progress | null;  // the /api/diff answer's `progress`, once it came
  ai?: AiStep | null;        // the AI step, if this page has one
  times: Times;
}>(), { result: null, ai: null });
const api = inject(API)!;
const polled = ref<Progress | null>(null), now = ref(performance.now());

const finished = () => !!props.result && (!props.ai || props.times.aiDone != null);
async function poll() {
  if (props.result) return;
  try {
    const p = await api.get<Progress>("/api/progress", { title: props.title });
    // Once the request is over its entry is gone: keep the last steps shown until the result replaces them.
    if (p.visited.length || !polled.value) polled.value = p;
  } catch { /* the result itself reports errors */ }
}
poll();
const timer = setInterval(() => { if (!finished()) { now.value = performance.now(); poll(); } }, 1000);
onBeforeUnmount(() => clearInterval(timer));

const fmt = (s: number) => `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;

type State = "done" | "active" | "skipped" | "todo";
interface Row { key: string; label: string; state: State; seconds?: number | null; detail?: string }
const steps = computed((): Row[] => {
  const p = props.result || polled.value;
  if (!p) return [];
  const visited: [string, number][] = p.visited.length ? p.visited : props.result ? [] : [[p.steps[0].key, 0]];  // starting
  const current = props.result ? null : visited[visited.length - 1][0];
  const last = p.steps.findIndex((s) => s.key === visited[visited.length - 1]?.[0]);
  // The server's seconds when the request ended, or now while it runs (the page's clock: same start).
  const serverEnd = props.result ? props.result.seconds : (now.value - props.times.start) / 1000;
  const out: Row[] = p.steps.map((s, i) => {
    const k = visited.findIndex(([key]) => key === s.key);
    if (k < 0) return { ...s, state: i < last || props.result ? "skipped" : "todo" };
    const begin = visited[k][1], end = k + 1 < visited.length ? visited[k + 1][1] : serverEnd;
    return s.key === current ? { ...s, state: "active", seconds: end - begin, detail: polled.value?.detail }
      : { ...s, state: "done", seconds: end - begin };
  });
  if (props.ai) {
    const { total, settled, failed } = props.ai;
    const begin = props.times.result, end = props.times.aiDone ?? now.value;
    out.push({
      key: "ai", label: "Explaining and translating the findings with AI",
      state: begin == null ? "todo" : !total ? "skipped" : props.times.aiDone != null ? "done" : "active",
      detail: `${settled} of ${total}${failed ? `, ${failed} failed` : ""}`,
      // the clock ticks each second: it may lag `begin`
      seconds: begin == null ? null : Math.max(0, end - begin) / 1000,
    });
  }
  return out;
});
const total = computed(() => {
  const end = props.ai ? props.times.aiDone : props.times.result;
  return ((end ?? now.value) - props.times.start) / 1000;
});
</script>

<template>
  <div class="loading">
    <!-- One live region that stays: screen readers hear each new step, not the seconds. -->
    <span class="sr-only" role="status">{{ steps.find((s) => s.state === "active")?.label ?? "" }}</span>
    <CdxProgressIndicator v-if="!steps.length">Comparing the editions</CdxProgressIndicator>
    <ol v-else class="steps" aria-label="Loading steps">
      <li v-for="s in steps" :key="s.key" :class="s.state" :aria-current="s.state === 'active' ? 'step' : undefined">
        <CdxProgressIndicator v-if="s.state === 'active'">In progress</CdxProgressIndicator>
        <CdxIcon v-else-if="s.state === 'done'" :icon="cdxIconCheck" icon-label="Done" />
        <CdxIcon v-else-if="s.state === 'skipped'" :icon="cdxIconSubtract" />
        <span v-else class="dot" aria-hidden="true"></span>
        <span>
          {{ s.label }}<span v-if="s.state === 'skipped'" class="muted">{{ " · not needed" }}</span>
          <span v-if="s.detail && (s.state === 'active' || (s.key === 'ai' && s.state === 'done'))" class="muted">{{ ` · ${s.detail}` }}</span>
          <span v-if="s.seconds != null && s.state !== 'todo'" class="muted time">{{ ` · ${fmt(s.seconds)}` }}</span>
        </span>
      </li>
      <li class="total"><span class="dot" aria-hidden="true"></span><span>Total{{ ` · ${fmt(total)}` }}</span></li>
    </ol>
    <p v-if="!finished()" class="muted">The first time an article is asked for, all its Wikipedia versions are fetched and embedded: this may take a few minutes.</p>
  </div>
</template>
