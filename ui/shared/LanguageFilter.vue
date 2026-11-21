<!-- What is shown, as a panel in the style of Wikipedia's "Appearance" menu: a ruled title, then one ruled
     section per filter. Kinds: checkboxes, each with how many findings the decision model found of it.
     Languages: a picker (a Codex popover of checkboxes; Apply asks the server again, comparing only
     those). Dialects (editions without a two-letter code): shown or hidden. -->
<script setup lang="ts">
import { computed, ref, watch, type ComponentPublicInstance } from "vue";
import { CdxButton, CdxCheckbox, CdxIcon, CdxPopover, CdxRadio } from "@wikimedia/codex";
import { cdxIconExpand } from "@wikimedia/codex-icons";
import type { Filters, Kind } from "./types";
import { KIND_NAMES, langName } from "./util";

const props = withDefaults(
  defineProps<{
    languages: string[];
    counts: Record<Kind, number>;
    langs?: string[] | null;
    dialects?: boolean;
    kinds?: Kind[] | null;
  }>(),
  { langs: null, dialects: false, kinds: null },
); // langs, kinds null: all
const emit = defineEmits<{ change: [Filters] }>();
const KINDS = Object.keys(KIND_NAMES) as Kind[];
const current = (): Filters => ({ langs: props.langs, dialects: props.dialects, kinds: props.kinds });

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
  emit("change", { ...current(), langs: chosen.value.length === props.languages.length ? null : [...chosen.value] });
};
const shownKinds = computed(() => props.kinds ?? KINDS);
// At least one kind stays on: unticking the last one is ignored.
const setKinds = (picked: Kind[]) => {
  if (picked.length) emit("change", { ...current(), kinds: picked.length === KINDS.length ? null : picked });
};
</script>

<template>
  <aside class="filters" aria-labelledby="filters-title">
    <div class="filters-head"><b id="filters-title">Filters</b></div>
    <fieldset>
      <legend>Kinds</legend>
      <CdxCheckbox v-for="k in KINDS" :key="k" :model-value="shownKinds" :input-value="k" @update:model-value="setKinds"
        >{{ KIND_NAMES[k] }} <span class="count">{{ counts[k] }}</span></CdxCheckbox
      >
    </fieldset>
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
        @update:model-value="emit('change', { ...current(), dialects: true })"
        >Show</CdxRadio
      >
      <CdxRadio
        :model-value="dialects ? 'show' : 'hide'"
        name="dialects"
        input-value="hide"
        @update:model-value="emit('change', { ...current(), dialects: false })"
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
