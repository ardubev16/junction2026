<!-- While /api/diff works: its steps (from /api/progress, polled each second while shown), each done one
     checked, the current one spinning with its detail and the seconds so far, the ones this request did not
     need marked as such, the rest to come. -->
<script setup>
import { computed, inject, onBeforeUnmount, ref } from "vue";
import { CdxIcon, CdxProgressIndicator } from "@wikimedia/codex";
import { cdxIconCheck, cdxIconSubtract } from "@wikimedia/codex-icons";

const props = defineProps({ title: { type: String, required: true } });
const api = inject("api");
const progress = ref(null);

async function poll() {
  try {
    const p = await api.get("/api/progress", { title: props.title });
    // Once the request is over its entry is gone: keep the last steps shown until the result replaces them.
    if (p.visited.length || !progress.value) progress.value = p;
  } catch { /* the result itself reports errors */ }
}
poll();
const timer = setInterval(poll, 1000);
onBeforeUnmount(() => clearInterval(timer));

const steps = computed(() => {
  const p = progress.value;
  if (!p) return [];
  const current = p.visited.at(-1) ?? p.steps[0].key;  // not registered yet: it is starting
  const at = p.steps.findIndex((s) => s.key === current);
  return p.steps.map((s, i) => ({
    ...s,
    state: s.key === current ? "active" : p.visited.includes(s.key) ? "done" : i < at ? "skipped" : "todo",
  }));
});
</script>

<template>
  <div class="loading">
    <!-- One live region that stays: screen readers hear each new step, not the seconds. -->
    <span class="sr-only" role="status">{{ steps.find((s) => s.state === "active")?.label ?? "Comparing the editions" }}</span>
    <CdxProgressIndicator v-if="!steps.length">Comparing the editions</CdxProgressIndicator>
    <ol v-else class="steps" aria-label="Comparing the editions">
      <li v-for="s in steps" :key="s.key" :class="s.state" :aria-current="s.state === 'active' ? 'step' : null">
        <CdxProgressIndicator v-if="s.state === 'active'">In progress</CdxProgressIndicator>
        <CdxIcon v-else-if="s.state === 'done'" :icon="cdxIconCheck" icon-label="Done" />
        <CdxIcon v-else-if="s.state === 'skipped'" :icon="cdxIconSubtract" />
        <span v-else class="dot" aria-hidden="true"></span>
        <span>
          {{ s.label }}<template v-if="s.state === 'skipped'"><span class="muted"> · not needed</span></template>
          <span v-if="s.state === 'active'" class="muted">{{ progress.detail ? ` · ${progress.detail}` : "" }}{{ ` · ${progress.seconds} s` }}</span>
        </span>
      </li>
    </ol>
    <p class="muted">The first time an article is asked for, all its Wikipedia versions are fetched and embedded: this may take a few minutes.</p>
  </div>
</template>
