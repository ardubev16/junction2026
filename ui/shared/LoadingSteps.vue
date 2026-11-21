<!-- The steps of loading a topic, the AI's included, each with its seconds, and the total, all as the
     server measured them: from /api/progress, polled each second until `result` (the /api/diff answer's
     `progress`) has them all. Done steps are checked, the current one spins with its detail, steps the
     request did not need are marked so, the rest are to come. -->
<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref } from "vue";
import { CdxIcon, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconCheck, cdxIconSubtract } from "@wikimedia/codex-icons";
import { API, type Progress } from "./types";

const props = withDefaults(
  defineProps<{
    title: string;
    result?: Progress | null; // the /api/diff answer's `progress`, once it came
  }>(),
  { result: null },
);
const api = inject(API)!;
const polled = ref<Progress | null>(null);

async function poll() {
  if (props.result) return;
  try {
    const p = await api.get<Progress>("/api/progress", { title: props.title });
    // Once the request is over its entry is gone: keep the last steps shown until the result replaces them.
    if (p.visited.length || !polled.value) polled.value = p;
  } catch {
    /* the result itself reports errors */
  }
}
poll();
const timer = setInterval(() => {
  if (!props.result) poll();
}, 1000);
onBeforeUnmount(() => clearInterval(timer));

const fmt = (s: number) => `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
const progress = computed(() => props.result || polled.value);

type State = "done" | "active" | "skipped" | "todo";
interface Row {
  key: string;
  label: string;
  state: State;
  seconds?: number;
  detail?: string;
}
const steps = computed((): Row[] => {
  const p = progress.value;
  if (!p) return [];
  const visited: [string, number][] = p.visited.length ? p.visited : props.result ? [] : [[p.steps[0].key, 0]]; // starting
  const current = props.result ? null : visited[visited.length - 1][0];
  const last = p.steps.findIndex((s) => s.key === visited[visited.length - 1]?.[0]);
  return p.steps.map((s, i) => {
    const k = visited.findIndex(([key]) => key === s.key);
    if (k < 0) return { ...s, state: i < last || props.result ? "skipped" : "todo" };
    const seconds = (k + 1 < visited.length ? visited[k + 1][1] : p.seconds) - visited[k][1];
    // The last step keeps its count once done ("1511 of 1511").
    const detail = s.key === current || (s.key === "decide" && props.result) ? p.detail : undefined;
    return { ...s, state: s.key === current ? "active" : "done", seconds: Math.max(0, seconds), detail };
  });
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
          <span v-if="s.detail" class="muted">{{ ` · ${s.detail}` }}</span>
          <span v-if="s.seconds != null" class="muted time">{{ ` · ${fmt(s.seconds)}` }}</span>
        </span>
      </li>
      <li class="total">
        <span class="dot" aria-hidden="true"></span><span>Total{{ ` · ${fmt(progress?.seconds ?? 0)}` }}</span>
      </li>
    </ol>
    <p v-if="!result" class="muted">
      The first time an article is asked for, all its Wikipedia versions are fetched and embedded: this may take a few
      minutes.
    </p>
  </div>
</template>
