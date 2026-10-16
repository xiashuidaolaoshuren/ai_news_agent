<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import { renderMarkdown } from '@/lib/markdown'
import { plainText, truncateAt } from '@/lib/revealHtml'
import { createStreamReveal } from '@/lib/streamReveal'

const props = defineProps<{ text: string; streaming?: boolean; ended?: boolean }>()

const emit = defineEmits<{ revealed: [] }>()

const html = computed(() => renderMarkdown(props.text))

/** How much of the reply the paced reveal has put on screen, and whether it is done. */
const revealed = ref(0)
const finished = ref(false)

const reveal = createStreamReveal()

/** The reply block, used to find the transcript's scroll container while it types. */
const root = ref<HTMLElement | null>(null)

/** The nearest ancestor that actually scrolls, which is the transcript column. */
function scrollHost(from: HTMLElement | null): HTMLElement | null {
  for (let node = from?.parentElement ?? null; node !== null; node = node.parentElement) {
    const overflowY = getComputedStyle(node).overflowY
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > 0) {
      return node
    }
  }
  return null
}

/**
 * The prototype follows the reply down the transcript on every reveal step, but
 * only while the reader is already near the bottom.
 */
function follow(within = 200): void {
  const host = scrollHost(root.value)
  if (host === null) {
    return
  }
  if (host.scrollHeight - host.scrollTop - host.clientHeight < within) {
    host.scrollTop = host.scrollHeight
  }
}

reveal.watch(() => {
  revealed.value = reveal.revealed()
  follow()
  if (reveal.finished()) {
    finished.value = true
    emit('revealed')
  }
})

/**
 * The reveal counts characters against the plain text of the render, which is the
 * same count `truncateAt` cuts at. A loaded reply is not paced at all.
 */
watch(
  () => (props.streaming === true ? plainText(html.value) : ''),
  (plain) => {
    if (props.streaming === true) {
      reveal.received(plain)
    }
  },
  { immediate: true },
)

watch(
  () => props.ended === true,
  (ended) => {
    if (ended && props.streaming === true) {
      reveal.end()
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  // A reply that leaves the screen mid-reveal hands the transcript straight back,
  // so the store does not wait on a reveal that is no longer there.
  if (props.streaming === true && !finished.value) {
    emit('revealed')
  }
  reveal.stop()
})

const rendered = computed(() =>
  props.streaming === true && !finished.value
    ? truncateAt(html.value, revealed.value)
    : html.value,
)
</script>

<template>
  <div
    ref="root"
    class="md"
    :class="{ streaming: props.streaming === true }"
    data-od-id="markdown-reply"
    v-html="rendered"
  ></div>
</template>
