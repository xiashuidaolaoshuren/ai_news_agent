<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ text: string | null }>()

/**
 * Blank-line-separated paragraphs of plain text.
 *
 * The API text is untrusted and never rendered as HTML, so every paragraph goes
 * through Vue's text interpolation.
 */
const paragraphs = computed(() =>
  (props.text ?? '')
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter((part) => part !== ''),
)
</script>

<template>
  <p v-for="(part, index) in paragraphs" :key="index">{{ part }}</p>
</template>
