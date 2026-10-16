<script setup lang="ts">
import { computed, onMounted, onUnmounted, useTemplateRef, watch } from 'vue'

import Sidebar from '@/components/sidebar/Sidebar.vue'
import AppShell from '@/components/shell/AppShell.vue'
import ChatHead from '@/components/shell/ChatHead.vue'
import Composer from '@/components/composer/Composer.vue'
import HistoryPanel from '@/components/history/HistoryPanel.vue'
import Thread from '@/components/thread/Thread.vue'
import { useComposerStore } from '@/stores/composer'
import { useHistoryStore } from '@/stores/history'
import { useSessionsStore } from '@/stores/sessions'
import { useThemeStore } from '@/stores/theme'
import { useThreadStore } from '@/stores/thread'

const themeStore = useThemeStore()
const sessions = useSessionsStore()
const thread = useThreadStore()
const composer = useComposerStore()
const history = useHistoryStore()

const shell = useTemplateRef<InstanceType<typeof AppShell>>('shell')
const composerField = useTemplateRef<InstanceType<typeof Composer>>('composerField')

/** An open inline edit in the sidebar takes Escape before the shell closes overlays. */
const inlineEditOpen = computed(
  () => sessions.renamingId !== null || sessions.deleteId !== null,
)

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !inlineEditOpen.value) {
    return
  }
  if (sessions.renamingId !== null) {
    sessions.cancelRename()
    return
  }
  sessions.cancelDelete()
}

// The prototype dismisses the sidebar overlay as soon as a conversation is chosen.
watch(
  () => sessions.activeId,
  (activeId) => {
    shell.value?.closeSidebar()
    void thread.openSession(sessions.sessions.find((item) => item.id === activeId) ?? null)
  },
)

onMounted(() => {
  themeStore.initFromDocument()
  document.addEventListener('keydown', onKeydown)
  void sessions.loadSessions()
  void sessions.loadHealth()
  void composer.load()
})

// A suggestion, a follow-up, or Run again puts text in the dock and returns the caret.
watch(
  () => composer.focusToken,
  () => {
    composerField.value?.focus()
  },
)

/**
 * "Ask in chat" on an opened history result: hand the title to the composer, and
 * step out of the way only when the panel covers the dock.
 */
function onHistoryAsk(title: string): void {
  history.askInChat(title)
  shell.value?.closeHistoryIfOverlay()
}

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <AppShell ref="shell" :escape-guard="inlineEditOpen">
    <template #sidebar>
      <Sidebar />
    </template>

    <template #header>
      <ChatHead
        :hist-open="shell?.histOpen ?? false"
        @open-sidebar="shell?.openSidebar()"
        @toggle-history="shell?.toggleHistory()"
      />
    </template>

    <template #default>
      <Thread
        :messages="thread.visibleMessages"
        :fresh-ids="thread.freshIds"
        :run="thread.run"
        :cancelled="thread.cancelled"
        :alert="thread.alert"
        @run-again="composer.runAgain()"
        @followup="composer.prefillFollowUp($event)"
        @suggest="composer.prefill($event)"
        @reveal-done="thread.revealFinished()"
      />
    </template>

    <template #composer>
      <Composer
        ref="composerField"
        :vm="composer.vm"
        @send="composer.send()"
        @cancel="composer.cancel()"
        @update-text="composer.setText($event)"
        @toggle-source="composer.toggleSource($event)"
        @commit-count="composer.commitCount($event)"
        @step-count="composer.stepCount($event)"
      />
    </template>

    <template #history>
      <HistoryPanel
        :vm="history.vm"
        @update-filter="history.setFilters($event)"
        @clear="history.clearFilters()"
        @retry="history.retry()"
        @open="history.open($event)"
        @close-result="history.closeResult()"
        @ask="onHistoryAsk($event)"
        @close="shell?.closeHistory()"
      />
    </template>
  </AppShell>
</template>
