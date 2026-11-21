<!-- The numbers behind a finding, in a Codex popover behind an "i" button: the decision model's verdict
     first, then how the quotes were matched and the tone axis that made them a candidate. Short: the
     About page explains each number. -->
<script setup lang="ts">
import { computed, inject, ref, type ComponentPublicInstance } from "vue";
import { CdxButton, CdxIcon, CdxPopover } from "@wikimedia/codex";
import { cdxIconInfo } from "@wikimedia/codex-icons";
import { API, type Finding } from "./types";
import { KIND_NAMES, langName, sigma } from "./util";

const props = defineProps<{ finding: Finding }>();
const api = inject(API)!;
const open = ref(false),
  anchor = ref<ComponentPublicInstance | null>(null);
const d = computed(() => props.finding.decision);
// The strength score (0–2) as its nearest level.
const strength = computed(() => (d.value ? ["minor", "notable", "major"][Math.round(d.value.strength)] : ""));
// The edition furthest along the tone axis: why this became a candidate, whoever stands apart in fact.
const axisLang = computed(() =>
  Object.entries(props.finding.deviations).reduce((a, b) => (Math.abs(b[1]) > Math.abs(a[1]) ? b : a)),
);
</script>

<template>
  <CdxButton
    ref="anchor"
    weight="quiet"
    size="small"
    class="info"
    data-popover-anchor
    aria-label="The numbers behind this finding"
    @click="open = !open"
  >
    <CdxIcon :icon="cdxIconInfo" size="small" />
  </CdxButton>
  <CdxPopover
    v-model:open="open"
    :anchor="anchor"
    placement="bottom-end"
    class="numbers"
    use-close-button
    title="The numbers behind this finding"
  >
    <table>
      <tr>
        <th scope="row">Decision model</th>
        <td v-if="d">
          {{ KIND_NAMES[d.kind] }}, {{ Math.round(d.real * 100) }}% likely a disagreement; {{ strength }} ({{
            d.strength.toFixed(1)
          }}
          of 2)
        </td>
        <td v-else>not checked</td>
      </tr>
      <tr v-if="d?.outlier">
        <th scope="row">Stands apart</th>
        <td>{{ langName(d.outlier) }}</td>
      </tr>
      <tr>
        <th scope="row">Match</th>
        <td>distance {{ finding.distance.toFixed(2) }} (one statement up to 0.35)</td>
      </tr>
      <tr>
        <th scope="row">Tone</th>
        <td>{{ langName(axisLang[0]) }} {{ sigma(axisLang[1]) }} on the {{ finding.axis }} axis</td>
      </tr>
    </table>
    <a :href="`${api.about}#numbers`" target="_blank" rel="noopener">What these numbers mean</a>
  </CdxPopover>
</template>
