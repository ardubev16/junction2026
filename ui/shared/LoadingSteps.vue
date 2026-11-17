<!-- The steps of loading a topic, each with its seconds, and the total: the server's (from /api/progress,
     polled each second until `result`, the /api/diff answer's `progress`, has them all), then, in the web
     app, the AI explaining and translating the page's findings (`ai`). Done steps are checked, the current
     one spins with its detail, steps the request did not need are marked so, the rest are to come.
     `times` (performance.now() values: start, result, aiDone) belong to the page, so the list can be shown
     again once loaded. -->
<script setup>
import { computed, inject, onBeforeUnmount, ref } from "vue";
import { CdxIcon, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconCheck, cdxIconSubtract } from "@wikimedia/codex-icons";

const props = defineProps({
  title: { type: String, required: true },
  result: { type: Object, default: null },  // the /api/diff answer's `progress`, once it came
  ai: { type: Object, default: null },      // { total, settled, failed }: the AI step, if this page has one
  times: { type: Object, required: true },
});
const api = inject("api");
const polled = ref(null), now = ref(performance.now());

const finished = () => props.result && (!props.ai || props.times.aiDone != null);
async function poll() {
  if (props.result) return;
  try {
    const p = await api.get("/api/progress", { title: props.title });
    // Once the request is over its entry is gone: keep the last steps shown until the result replaces them.
    if (p.visited.length || !polled.value) polled.value = p;
  } catch { /* the result itself reports errors */ }
}
poll();
const timer = setInterval(() => { if (!finished()) { now.value = performance.now(); poll(); } }, 1000);
onBeforeUnmount(() => clearInterval(timer));

const secs = (ms) => ms / 1000;
const fmt = (s) => `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;

const steps = computed(() => {
  const p = props.result || polled.value;
  if (!p) return [];
  const visited = p.visited.length ? p.visited : props.result ? [] : [[p.steps[0].key, 0]];  // starting
  const current = props.result ? null : visited.at(-1)[0];
  const last = p.steps.findIndex((s) => s.key === visited.at(-1)?.[0]);
  // The server's seconds when the request ended, or now while it runs (the page's clock: same start).
  const serverEnd = props.result ? props.result.seconds : secs(now.value - props.times.start);
  const out = p.steps.map((s, i) => {
    const k = visited.findIndex(([key]) => key === s.key);
    if (k < 0) return { ...s, state: i < last || props.result ? "skipped" : "todo" };
    const begin = visited[k][1], end = k + 1 < visited.length ? visited[k + 1][1] : serverEnd;
    return { ...s, state: s.key === current ? "active" : "done", seconds: end - begin };
  });
  if (props.ai) {
    const { total, settled, failed } = props.ai;
    const begin = props.times.result, end = props.times.aiDone ?? now.value;
    out.push({
      key: "ai", label: "Explaining and translating the findings with AI",
      state: begin == null ? "todo" : !total ? "skipped" : props.times.aiDone != null ? "done" : "active",
      detail: `${settled} of ${total}${failed ? `, ${failed} failed` : ""}`,
      seconds: begin == null ? null : secs(Math.max(0, end - begin)),  // the clock ticks each second: may lag `begin`
    });
  }
  return out;
});
const detail = (s) => (s.key === "ai" ? s.detail : polled.value?.detail);
const total = computed(() => {
  const end = props.ai ? props.times.aiDone : props.times.result;
  return secs((end ?? now.value) - props.times.start);
});
</script>

<template>
  <div class="loading">
    <!-- One live region that stays: screen readers hear each new step, not the seconds. -->
    <span class="sr-only" role="status">{{ steps.find((s) => s.state === "active")?.label ?? "" }}</span>
    <CdxProgressIndicator v-if="!steps.length">Comparing the editions</CdxProgressIndicator>
    <ol v-else class="steps" aria-label="Loading steps">
      <li v-for="s in steps" :key="s.key" :class="s.state" :aria-current="s.state === 'active' ? 'step' : null">
        <CdxProgressIndicator v-if="s.state === 'active'">In progress</CdxProgressIndicator>
        <CdxIcon v-else-if="s.state === 'done'" :icon="cdxIconCheck" icon-label="Done" />
        <CdxIcon v-else-if="s.state === 'skipped'" :icon="cdxIconSubtract" />
        <span v-else class="dot" aria-hidden="true"></span>
        <span>
          {{ s.label }}<span v-if="s.state === 'skipped'" class="muted">{{ " · not needed" }}</span>
          <span v-if="s.state === 'active' || (s.key === 'ai' && s.state === 'done')" class="muted">{{ detail(s) ? ` · ${detail(s)}` : "" }}</span>
          <span v-if="s.seconds != null && s.state !== 'todo'" class="muted time">{{ ` · ${fmt(s.seconds)}` }}</span>
        </span>
      </li>
      <li class="total"><span class="dot" aria-hidden="true"></span><span>Total{{ ` · ${fmt(total)}` }}</span></li>
    </ol>
    <p v-if="!finished()" class="muted">The first time an article is asked for, all its Wikipedia versions are fetched and embedded: this may take a few minutes.</p>
  </div>
</template>
