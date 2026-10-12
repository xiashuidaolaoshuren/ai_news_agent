<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

import { hoverPreview, registerHoverCard } from '@/lib/useHoverPreview'

const card = ref<HTMLElement | null>(null)

onMounted(() => {
  registerHoverCard(card.value)
})

onUnmounted(() => {
  registerHoverCard(null)
})
</script>

<template>
  <div
    v-show="hoverPreview.visible"
    ref="card"
    class="hovercard"
    role="tooltip"
    :style="{ top: `${hoverPreview.top}px`, left: `${hoverPreview.left}px` }"
  >
    <img :src="hoverPreview.src ?? ''" :alt="hoverPreview.alt" width="1200" height="600" />
  </div>
</template>
