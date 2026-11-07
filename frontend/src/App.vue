<script setup lang="ts">
import { computed, onMounted, onUnmounted, useTemplateRef, watch } from 'vue'

import Sidebar from '@/components/sidebar/Sidebar.vue'
import AppShell from '@/components/shell/AppShell.vue'
import ChatHead from '@/components/shell/ChatHead.vue'
import Composer from '@/components/composer/Composer.vue'
import HistoryPanel from '@/components/history/HistoryPanel.vue'
import Thread from '@/components/thread/Thread.vue'
import SettingsDialog from '@/components/settings/SettingsDialog.vue'
import { useComposerStore } from '@/stores/composer'
import { useHistoryStore } from '@/stores/history'
import { useSessionsStore } from '@/stores/sessions'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { useThreadStore } from '@/stores/thread'
import type { OutputLanguage } from '@/stores/settings'
import type { SourceProfileVm } from '@/vm/settings'
import type { RefVm } from '@/vm/types'

const themeStore = useThemeStore()
const sessions = useSessionsStore()
const thread = useThreadStore()
const composer = useComposerStore()
const settings = useSettingsStore()
const history = useHistoryStore()

const shell = useTemplateRef<InstanceType<typeof AppShell>>('shell')
const composerField = useTemplateRef<InstanceType<typeof Composer>>('composerField')
const threadView = useTemplateRef<InstanceType<typeof Thread>>('threadView')

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

/**
 * A run or a preference save replaces the record in the sidebar. The thread reads
 * the conversation's stored sources, so hand the fresh record over as well.
 */
watch(
  () => sessions.sessions.find((item) => item.id === sessions.activeId),
  (next) => {
    thread.syncSession(next ?? null)
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
 * "Ask in chat" on an opened history result: set the composer's follow-up target.
 */
function onHistoryAsk(ref: RefVm): void {
  history.askInChat(ref)
  shell.value?.closeHistoryIfOverlay()
}

function onHistoryDeepDive(ref: RefVm): void {
  void composer.deepDive(ref)
  shell.value?.closeHistoryIfOverlay()
}

function onHistoryGotoRelated(ref: RefVm): void {
  threadView.value?.gotoRef(ref)
}

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <AppShell ref="shell" :escape-guard="inlineEditOpen">
    <template #sidebar>
      <Sidebar @open-settings="settings.open('sources')" />
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
        ref="threadView"
        :messages="thread.visibleMessages"
        :fresh-ids="thread.freshIds"
        :run="thread.run"
        :cancelled="thread.cancelled"
        :alert="thread.alert"
        :live-digest="thread.liveDigest"
        :can-load-older="thread.nextCursor !== null"
        :loading-older="thread.loadingOlder"
        :loading="thread.opening || (sessions.loading && sessions.activeId === null)"
        :load-error="thread.loadError"
        :catalog="composer.sources"
        @load-older="thread.loadOlder()"
        @retry-load="thread.retryLoad()"
        @repeat="composer.repeat($event)"
        @run-again="composer.runAgain()"
        @retry-poll="thread.retryPoll()"
        @deepdive="composer.deepDive($event)"
        @ask="composer.askAbout($event)"
        @suggest="composer.prefill($event)"
        @reveal-done="thread.revealFinished()"
        @confirm-juya="thread.confirmJuya($event.messageId, $event.action)"
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
        @remove-ref="composer.removeRef()"
        @open-settings="settings.open('sources', $event)"
        @dismiss-counts="settings.dismissCounts()"
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
        @deepdive="onHistoryDeepDive($event)"
        @ask="onHistoryAsk($event)"
        @goto-related="onHistoryGotoRelated($event)"
        @close="shell?.closeHistory()"
      />
    </template>
  </AppShell>
  <SettingsDialog
    :vm="{
      open: settings.isOpen,
      tab: settings.tab,
      language: settings.draft.language,
      profiles: settings.draft.profiles,
      fieldErrors: settings.fieldErrors,
      saved: settings.saved,
      loadError: settings.loadError,
      focus: settings.focus,
    }"
    @close="settings.close()"
    @save="settings.save()"
    @retry="settings.load()"
    @update-language="settings.draft.language = $event as OutputLanguage"
    @update-profile="settings.updateProfile($event as SourceProfileVm)"
  />
</template>
