<!-- Which editions are compared: a language picker (a Codex popover of checkboxes; Apply asks the server
     again, comparing only those) and a quick "Hide dialects" (editions without a two-letter code). -->
<script setup lang="ts">
import { computed, ref, watch, type ComponentPublicInstance } from "vue";
import { CdxButton, CdxCheckbox, CdxIcon, CdxPopover } from "@wikimedia/codex";
import { cdxIconExpand } from "@wikimedia/codex-icons";
import type { Filters } from "./types";
import { langName } from "./util";

const props = withDefaults(defineProps<{ languages: string[]; langs?: string[] | null; dialects?: boolean }>(), {
  langs: null,
  dialects: true,
}); // langs null: all
const emit = defineEmits<{ change: [Filters] }>();
const open = ref(false),
  anchor = ref<ComponentPublicInstance | null>(null),
  chosen = ref<string[]>([]);
const sorted = computed(() => [...props.languages].sort((a, b) => langName(a).localeCompare(langName(b))));
watch(open, (o) => {
  if (o) chosen.value = [...(props.langs || props.languages)];
});
const label = computed(() =>
  props.langs
    ? `Languages: ${props.langs.length} of ${props.languages.length}`
    : `Languages: all ${props.languages.length}`,
);
const apply = () => {
  open.value = false;
  emit("change", {
    langs: chosen.value.length === props.languages.length ? null : [...chosen.value],
    dialects: props.dialects,
  });
};
</script>

<template>
  <div class="filters">
    <CdxButton ref="anchor" weight="quiet" action="progressive" data-popover-anchor @click="open = !open">
      {{ label }} <CdxIcon :icon="cdxIconExpand" size="small" />
    </CdxButton>
    <CdxPopover
      v-model:open="open"
      :anchor="anchor"
      placement="bottom-start"
      class="picker"
      title="Languages compared"
      use-close-button
      :primary-action="{ label: 'Apply', actionType: 'progressive', disabled: chosen.length < 2 }"
      :default-action="{ label: 'Cancel' }"
      @primary="apply"
      @default="open = false"
    >
      <div class="actions">
        <CdxButton size="small" @click="chosen = [...languages]">All</CdxButton>
        <CdxButton size="small" @click="chosen = []">None</CdxButton>
      </div>
      <div class="columns">
        <CdxCheckbox v-for="l in sorted" :key="l" v-model="chosen" :input-value="l"
          >{{ langName(l) }} ({{ l }})</CdxCheckbox
        >
      </div>
    </CdxPopover>
    <CdxCheckbox
      :model-value="!dialects"
      inline
      @update:model-value="(hide) => emit('change', { langs, dialects: !hide })"
    >
      Hide dialects
    </CdxCheckbox>
  </div>
</template>
