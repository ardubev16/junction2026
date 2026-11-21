<!-- Which editions are compared, as a panel in the style of Wikipedia's "Appearance" menu: a ruled title
     with a "hide" button, then one ruled section per filter. Languages: a picker (a Codex popover of
     checkboxes; Apply asks the server again, comparing only those). Dialects (editions without a
     two-letter code): shown or hidden. Hidden, the panel is one "Filters" button; remembered per browser. -->
<script setup lang="ts">
import { computed, ref, watch, type ComponentPublicInstance } from "vue";
import { CdxButton, CdxCheckbox, CdxIcon, CdxPopover, CdxRadio } from "@wikimedia/codex";
import { cdxIconExpand, cdxIconFunnel } from "@wikimedia/codex-icons";
import type { Filters } from "./types";
import { langName } from "./util";

const props = withDefaults(defineProps<{ languages: string[]; langs?: string[] | null; dialects?: boolean }>(), {
  langs: null,
  dialects: true,
}); // langs null: all
const emit = defineEmits<{ change: [Filters] }>();
const HIDDEN = "wikicross-filters-hidden";
const hidden = ref(localStorage.getItem(HIDDEN) === "1");
watch(hidden, (h) => localStorage.setItem(HIDDEN, h ? "1" : "0"));
const open = ref(false),
  anchor = ref<ComponentPublicInstance | null>(null),
  chosen = ref<string[]>([]);
const sorted = computed(() => [...props.languages].sort((a, b) => langName(a).localeCompare(langName(b))));
watch(open, (o) => {
  if (o) chosen.value = [...(props.langs || props.languages)];
});
const label = computed(() =>
  props.langs ? `${props.langs.length} of ${props.languages.length}` : `All ${props.languages.length}`,
);
const apply = () => {
  open.value = false;
  emit("change", {
    langs: chosen.value.length === props.languages.length ? null : [...chosen.value],
    dialects: props.dialects,
  });
};
const setDialects = (shown: boolean) => emit("change", { langs: props.langs, dialects: shown });
</script>

<template>
  <CdxButton v-if="hidden" class="filters-show" weight="quiet" @click="hidden = false">
    <CdxIcon :icon="cdxIconFunnel" size="small" /> Filters
  </CdxButton>
  <aside v-else class="filters" aria-labelledby="filters-title">
    <div class="filters-head">
      <b id="filters-title">Filters</b>
      <CdxButton size="small" @click="hidden = true">hide</CdxButton>
    </div>
    <fieldset>
      <legend>Languages</legend>
      <CdxButton ref="anchor" weight="quiet" action="progressive" data-popover-anchor @click="open = !open">
        {{ label }} <CdxIcon :icon="cdxIconExpand" size="small" />
      </CdxButton>
    </fieldset>
    <fieldset>
      <legend>Dialects</legend>
      <CdxRadio
        :model-value="dialects ? 'show' : 'hide'"
        name="dialects"
        input-value="show"
        @update:model-value="setDialects(true)"
        >Show</CdxRadio
      >
      <CdxRadio
        :model-value="dialects ? 'show' : 'hide'"
        name="dialects"
        input-value="hide"
        @update:model-value="setDialects(false)"
        >Hide</CdxRadio
      >
    </fieldset>
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
  </aside>
</template>
