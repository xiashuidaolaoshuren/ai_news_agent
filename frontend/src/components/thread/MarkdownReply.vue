<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from '@/lib/markdown'

const props = defineProps<{ text: string; streaming?: boolean }>()

/**
 * While a reply streams, the caret sits at the end of the last block, as the
 * prototype's truncation helper leaves it.
 */
const html = computed(() => {
  const rendered = renderMarkdown(props.text)
  if (props.streaming !== true) {
    return rendered
  }
  const lastTag = rendered.lastIndexOf('</')
  if (lastTag === -1) {
    return `${rendered}<span class="caret"></span>`
  }
  return `${rendered.slice(0, lastTag)}<span class="caret"></span>${rendered.slice(lastTag)}`
})
</script>

<template>
  <div
    class="md"
    :class="{ streaming: props.streaming === true }"
    data-od-id="markdown-reply"
    v-html="html"
  ></div>
</template>
