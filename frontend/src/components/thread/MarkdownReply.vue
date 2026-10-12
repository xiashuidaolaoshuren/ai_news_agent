<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from '@/lib/markdown'

const props = defineProps<{ text: string }>()

const html = computed(() => renderMarkdown(props.text))
</script>

<template>
  <div class="md" data-od-id="markdown-reply" v-html="html"></div>
</template>
