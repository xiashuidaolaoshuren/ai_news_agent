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

<style scoped>
.theme-sw {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 34px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--fg);
  font-size: 12.5px;
  font-weight: 500;
  text-align: left;
  transition: background-color var(--d1) var(--ease);
}

.theme-sw:hover {
  background: var(--hover);
}

.theme-sw > .ic {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: none;
  color: var(--muted);
}

.theme-sw .lbl {
  flex: 1;
}

.track {
  width: 30px;
  height: 18px;
  border-radius: 999px;
  background: var(--border-strong);
  position: relative;
  flex: none;
  transition:
    background-color var(--d2) var(--ease),
    transform var(--d2) var(--ease);
}

.track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: 0 1px 2px oklch(0% 0 0 / 0.25);
  transition: transform var(--d2) var(--ease);
}

.theme-sw[aria-checked='true'] .track {
  background: var(--fg);
}

.theme-sw[aria-checked='true'] .track::after {
  transform: translateX(12px);
}
</style>
