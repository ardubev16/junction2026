<!-- The numbers behind a finding: an "i" button opening a Codex popover. -->
<script setup lang="ts">
import { computed, ref, type ComponentPublicInstance } from "vue";
import { CdxButton, CdxIcon, CdxPopover } from "@wikimedia/codex";
import { cdxIconInfo } from "@wikimedia/codex-icons";
import type { Finding } from "./types";
import { langName, sigma } from "./util";

const props = defineProps<{ finding: Finding }>();
const open = ref(false), anchor = ref<ComponentPublicInstance | null>(null);
const rows = computed(() => Object.entries(props.finding.deviations).sort((a, b) => b[1] - a[1]));
const own = computed(() => props.finding.deviations[props.finding.lang] ?? props.finding.deviation);
</script>

<template>
  <CdxButton ref="anchor" weight="quiet" size="small" class="info" data-popover-anchor
             aria-label="The numbers behind this finding" title="The numbers behind this finding" @click="open = !open">
    <CdxIcon :icon="cdxIconInfo" size="small" />
  </CdxButton>
  <CdxPopover v-model:open="open" :anchor="anchor" placement="bottom-end" class="numbers" use-close-button
              :title="`How far apart: the ${finding.axis} axis`">
    <p>
      Each sentence has a position on this axis: towards +, an edition {{ finding.ends[0] }}; towards −, it {{ finding.ends[1] }}.
      Positions are measured against the language's own sentences, so 1σ is a typical spread within that language.
    </p>
    <p>
      {{ langName(finding.lang) }} sits {{ sigma(own) }} from the average of the others; a finding needs at least 1.2σ
      either way. Each edition, from its others' average:
    </p>
    <table>
      <tr v-for="[l, d] in rows" :key="l" :class="{ this: l === finding.lang }">
        <td>{{ langName(l) }}</td><td class="num">{{ sigma(d) }}</td>
      </tr>
    </table>
    <p class="muted">
      The sentences are matched as one statement: their largest cosine distance is {{ finding.distance.toFixed(2) }}
      (0 is the same meaning; up to 0.35 counts).
    </p>
  </CdxPopover>
</template>
