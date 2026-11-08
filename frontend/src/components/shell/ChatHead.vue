<script setup lang="ts">
import { computed, useTemplateRef } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useSessionsStore } from '@/stores/sessions'
import { useThemeStore } from '@/stores/theme'

const props = defineProps<{
  histOpen: boolean
  /** The transcript is still on its first load. */
  loading?: boolean
  /** The transcript request failed; the thread shows the retry panel. */
  loadFailed?: boolean
}>()

const emit = defineEmits<{ openSidebar: []; toggleHistory: [] }>()

const sessions = useSessionsStore()
const themeStore = useThemeStore()
const themeButton = useTemplateRef<HTMLButtonElement>('themeButton')

const title = computed(() => {
  const active = sessions.sessions.find((session) => session.id === sessions.activeId)
  return active?.title ?? 'New conversation'
})

/**
 * The prototype's meta line, in its order: a failed load outranks loading, and
 * only a transcript with messages counts digests.
 */
const countLabel = computed(() => {
  if (props.loadFailed === true) {
    return 'Not loaded'
  }
  if (props.loading === true) {
    return 'Loading…'
  }
  const active = sessions.sessions.find((session) => session.id === sessions.activeId)
  const count = active?.digest_count ?? 0
  return count === 0 ? 'Empty' : `${count} digest${count === 1 ? '' : 's'}`
})

const themeLabel = computed(() =>
  themeStore.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
)

/** Moon in light mode, sun in dark — same affordance as the prototype head toggle. */
const themeIcon = computed(() => (themeStore.theme === 'dark' ? 'sun' : 'moon'))

function onToggleTheme(event: MouseEvent): void {
  themeStore.toggleTheme(event, themeButton.value)
}
</script>

<template>
  <header class="chat-head" data-od-id="chat-head">
    <button
      type="button"
      class="icon-btn menu-btn"
      aria-label="Open conversations"
      @click="emit('openSidebar')"
    >
      <AppIcon name="menu" />
    </button>
    <h1 data-od-id="conversation-title">{{ title }}</h1>
    <span class="meta">{{ countLabel }}</span>
    <span class="grow" />
    <span
      v-if="sessions.fakeMode"
      class="badge-fake"
      title="The backend is serving fixture responses. No live connectors are called."
      data-od-id="fake-mode-badge"
    >
      <AppIcon name="flask" />FAKE MODE
    </span>
    <button
      ref="themeButton"
      type="button"
      class="icon-btn theme-btn"
      :aria-label="themeLabel"
      :title="themeLabel"
      data-od-id="theme-toggle"
      @click="onToggleTheme"
    >
      <AppIcon :name="themeIcon" />
    </button>
    <button
      type="button"
      class="btn btn-sm"
      :class="{ 'btn-ghost': !props.histOpen }"
      :aria-pressed="props.histOpen"
      aria-controls="history"
      data-od-id="history-toggle"
      @click="emit('toggleHistory')"
    >
      <AppIcon name="history" /><span class="btn-label">History</span>
    </button>
  </header>
</template>

<style scoped>
.chat-head {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}

.chat-head h1 {
  font: 600 15px/1.25 var(--font-display);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.chat-head .meta {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.grow {
  flex: 1;
}

.menu-btn {
  display: none;
}

@media (max-width: 899px) {
  .menu-btn {
    display: inline-grid;
  }

  .chat-head .meta {
    display: none;
  }
}

@media (max-width: 560px) {
  .btn-label {
    display: none;
  }
}
</style>
