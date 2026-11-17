<!-- Every edition, in a Codex popover: a topic can have dozens. Each link opens that edition. -->
<script setup>
import { ref } from "vue";
import { CdxButton, CdxIcon, CdxPopover } from "@wikimedia/codex";
import { cdxIconExpand } from "@wikimedia/codex-icons";
import { langName } from "../shared/util.js";

defineProps({ articles: { type: Array, required: true } });
const open = ref(false), anchor = ref(null);
const safe = (url) => (/^https?:\/\//.test(url) ? url : "#");
</script>

<template>
  <CdxButton ref="anchor" weight="quiet" action="progressive" @click="open = !open">
    {{ articles.length }} editions <CdxIcon :icon="cdxIconExpand" size="small" />
  </CdxButton>
  <CdxPopover v-model:open="open" :anchor="anchor" placement="bottom-end" class="editions" title="Editions" use-close-button>
    <div class="columns">
      <a v-for="a in articles" :key="a.lang" :href="safe(a.url)" target="_blank" rel="noopener">
        <b>{{ langName(a.lang) }} ({{ a.lang }})</b> · {{ a.title }}
      </a>
    </div>
  </CdxPopover>
</template>
