<!-- Every edition, in a Codex popover: a topic can have dozens. Each link opens that edition. -->
<script setup lang="ts">
import { ref, type ComponentPublicInstance } from "vue";
import { CdxButton, CdxIcon, CdxPopover } from "@wikimedia/codex";
import { cdxIconExpand } from "@wikimedia/codex-icons";
import type { Article } from "../shared/types";
import { langName } from "../shared/util";

defineProps<{ articles: Article[] }>();
const open = ref(false), anchor = ref<ComponentPublicInstance | null>(null);
const safe = (url: string) => (/^https?:\/\//.test(url) ? url : "#");
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
