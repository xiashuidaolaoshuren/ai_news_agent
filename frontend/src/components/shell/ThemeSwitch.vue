<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useTemplateRef } from 'vue'

import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const { theme } = storeToRefs(themeStore)
const rootEl = useTemplateRef<HTMLButtonElement>('rootEl')

function onClick(event: MouseEvent) {
  themeStore.toggleTheme(event, rootEl.value)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    themeStore.toggleTheme(
      { detail: 0, clientX: 0, clientY: 0 } as MouseEvent,
      rootEl.value,
    )
  }
}
</script>

<template>
  <button
    ref="rootEl"
    type="button"
    class="theme-sw"
    role="switch"
    :aria-checked="theme === 'dark'"
    data-od-id="theme-switch"
    @click="onClick"
    @keydown="onKeydown"
  >
    <svg class="ic" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
    <span class="lbl">Dark theme</span>
    <span class="track" aria-hidden="true" />
  </button>
</template>
