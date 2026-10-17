<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{ escapeGuard?: boolean }>()

const histOpen = ref(typeof window !== 'undefined' && window.innerWidth >= 1280)
const sbOpen = ref(false)

function closeOverlays() {
  if (sbOpen.value) {
    sbOpen.value = false
    return
  }
  if (histOpen.value && window.innerWidth < 1280) {
    histOpen.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    // An inline edit in the sidebar owns Escape while it is open.
    if (props.escapeGuard === true) {
      return
    }
    closeOverlays()
  }
}

function openSidebar() {
  sbOpen.value = true
}

function closeSidebar() {
  sbOpen.value = false
}

function toggleHistory() {
  histOpen.value = !histOpen.value
}

function closeHistory() {
  histOpen.value = false
}

/**
 * Dismiss the history panel only when it is overlaying the chat. At 1280px and
 * above it is a column, and an action inside it must not close the column.
 */
function closeHistoryIfOverlay() {
  if (window.innerWidth < 1280) {
    histOpen.value = false
  }
}

defineExpose({
  openSidebar,
  closeSidebar,
  toggleHistory,
  closeHistory,
  closeHistoryIfOverlay,
  histOpen,
  sbOpen,
})

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div
    class="app"
    :class="{ 'hist-open': histOpen, 'sb-open': sbOpen }"
    id="app-shell"
  >
    <aside class="sidebar" aria-label="Conversations">
      <slot name="sidebar" />
    </aside>
    <button
      type="button"
      class="scrim for-sb"
      aria-label="Close sidebar"
      tabindex="-1"
      @click="sbOpen = false"
    />

    <main class="chat">
      <slot name="header" />
      <div class="chat-body">
        <slot />
      </div>
      <slot name="composer" />
    </main>

    <button
      type="button"
      class="scrim for-hist"
      aria-label="Close history"
      tabindex="-1"
      @click="histOpen = false"
    />
    <aside class="history" id="history" aria-label="History search" data-od-id="history-panel">
      <slot name="history" />
    </aside>
  </div>
</template>

<style scoped>
.app {
  height: 100vh;
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr) 0;
  transition: grid-template-columns var(--d3) var(--ease);
}

.app.hist-open {
  grid-template-columns: 264px minmax(0, 1fr) 372px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--sunken);
  border-right: 1px solid var(--border);
}

.chat {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--bg);
}

.chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-left: 1px solid var(--border);
  overflow: hidden;
}

.scrim {
  display: none;
  position: fixed;
  inset: 0;
  background: var(--scrim);
  z-index: 20;
  border: 0;
  padding: 0;
}

@media (max-width: 1279px) {
  .app,
  .app.hist-open {
    grid-template-columns: 264px minmax(0, 1fr);
  }

  .history {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(392px, 92vw);
    z-index: 30;
    box-shadow: var(--shadow-lg);
    transform: translateX(105%);
    transition: transform var(--d3) var(--ease);
    background: var(--frost-panel);
    -webkit-backdrop-filter: blur(20px) saturate(1.2);
    backdrop-filter: blur(20px) saturate(1.2);
    border-left: none;
  }

  .app.hist-open .history {
    transform: none;
  }

  .app.hist-open .scrim.for-hist {
    display: block;
  }
}

@media (max-width: 899px) {
  .app,
  .app.hist-open {
    grid-template-columns: minmax(0, 1fr);
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    width: min(300px, 86vw);
    z-index: 30;
    box-shadow: var(--shadow-lg);
    transform: translateX(-105%);
    transition: transform var(--d3) var(--ease);
    background: var(--frost-side);
    -webkit-backdrop-filter: blur(20px) saturate(1.2);
    backdrop-filter: blur(20px) saturate(1.2);
  }

  .app.sb-open .sidebar {
    transform: none;
  }

  .app.sb-open .scrim.for-sb {
    display: block;
  }
}
</style>
