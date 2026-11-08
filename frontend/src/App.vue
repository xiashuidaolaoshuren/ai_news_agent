<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'

import Sidebar from '@/components/sidebar/Sidebar.vue'
import AppShell from '@/components/shell/AppShell.vue'
import ChatHead from '@/components/shell/ChatHead.vue'
import Composer from '@/components/composer/Composer.vue'
import HistoryPanel from '@/components/history/HistoryPanel.vue'
import Thread from '@/components/thread/Thread.vue'
import SettingsDialog from '@/components/settings/SettingsDialog.vue'
import SignIn from '@/components/settings/SignIn.vue'
import { useAuthStore } from '@/stores/auth'
import { useComposerStore } from '@/stores/composer'
import { useHistoryStore } from '@/stores/history'
import { useSessionsStore } from '@/stores/sessions'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { useThreadStore } from '@/stores/thread'
import type { OutputLanguage } from '@/stores/settings'
import type { KeyDraftKey, KeysVm, SourceProfileVm } from '@/vm/settings'
import type { RefVm } from '@/vm/types'

const themeStore = useThemeStore()
const sessions = useSessionsStore()
const thread = useThreadStore()
const composer = useComposerStore()
const settings = useSettingsStore()
const auth = useAuthStore()
const history = useHistoryStore()

/** The typed owner token while the sign-in screen is up; masked after a rejection. */
const signInToken = ref('')

const shell = useTemplateRef<InstanceType<typeof AppShell>>('shell')
const composerField = useTemplateRef<InstanceType<typeof Composer>>('composerField')
const threadView = useTemplateRef<InstanceType<typeof Thread>>('threadView')

/** The Keys panel reads the store's credential state; health comes from the catalog. */
const keysVm = computed<KeysVm>(() => ({
  readOnly: settings.credentials.readOnly,
  llmUnreadable: settings.credentials.llmUnreadable,
  draft: settings.keysDraft,
  rows: settings.credentials.rows,
  messages: settings.keysMessage,
  results: settings.testResults,
  testing: settings.testing,
  githubAuthError:
    composer.vm.sources.find((source) => source.name === 'github')?.health === 'auth_error',
}))

/** Any credential change can change a source's health; reload the catalog after it. */
async function afterCredentialChange(action: Promise<unknown>): Promise<void> {
  await action
  await composer.load()
}

function onKeysDraft(key: KeyDraftKey, value: string): void {
  settings.keysDraft[key] = value
}

function openSourceSection(name: string): void {
  settings.tab = 'sources'
  settings.focus = name
}

/** The Sources GitHub warning jumps to the token row on the Keys tab. */
function openKeysSection(): void {
  settings.tab = 'keys'
  settings.focus = 'github'
}

/** The newest digest in this conversation, for the history panel's opened note. */
const lastDigestRef = computed<string | null>(() => {
  for (let index = thread.visibleMessages.length - 1; index >= 0; index -= 1) {
    const ref = thread.visibleMessages[index]?.digest?.ref
    if (ref !== undefined && ref !== null) {
      return ref
    }
  }
  return null
})

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

/** Everything the shell needs from the API. Run on mount and again after sign-in. */
function loadAll(): void {
  void sessions.loadSessions()
  void sessions.loadHealth()
  void composer.load()
}

function onSignIn(token: string): void {
  void auth.submit(token)
}

/**
 * A 401 anywhere locks the app; accepting the owner token unlocks it and loads
 * the shell again. Closing Settings on lock keeps the dialog from reappearing
 * over the sign-in screen.
 */
watch(
  () => auth.locked,
  (locked) => {
    if (locked) {
      settings.close()
      return
    }
    loadAll()
  },
)

onMounted(() => {
  themeStore.initFromDocument()
  document.addEventListener('keydown', onKeydown)
  loadAll()
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

/** Cancelling a Juya confirmation leaves the prototype's note in the composer. */
function onConfirmJuya(payload: { messageId: number; action: 'continue' | 'cancel' }): void {
  if (payload.action === 'cancel') {
    composer.noteConfirmCancelled()
  }
  void thread.confirmJuya(payload.messageId, payload.action)
}

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <AppShell
    ref="shell"
    :escape-guard="inlineEditOpen"
    :inert="auth.locked || settings.isOpen"
  >
    <template #sidebar>
      <Sidebar @open-settings="settings.open('sources')" />
    </template>

    <template #header>
      <ChatHead
        :hist-open="shell?.histOpen ?? false"
        :loading="thread.opening"
        :load-failed="thread.loadError !== null"
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
        @confirm-juya="onConfirmJuya($event)"
        @open-settings="settings.open('sources', $event)"
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
        @dismiss-counts="composer.dismissCounts()"
      />
    </template>

    <template #history>
      <HistoryPanel
        :vm="history.vm"
        :conversation-digest="lastDigestRef"
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
  <SignIn
    v-if="auth.locked"
    v-model:token="signInToken"
    :error="auth.error"
    :busy="auth.busy"
    @submit="onSignIn"
  />
  <SettingsDialog
    v-if="!auth.locked"
    :vm="{
      open: settings.isOpen,
      tab: settings.tab,
      language: settings.draft.language,
      profiles: settings.draft.profiles,
      fieldErrors: settings.fieldErrors,
      saved: settings.saved,
      loadError: settings.loadError,
      focus: settings.focus,
      keys: keysVm,
    }"
    @close="settings.close()"
    @save="settings.save()"
    @retry="settings.load()"
    @set-tab="settings.tab = $event"
    @update-language="settings.draft.language = $event as OutputLanguage"
    @update-profile="settings.updateProfile($event as SourceProfileVm)"
    @update-keys-draft="onKeysDraft"
    @save-llm="afterCredentialChange(settings.saveLlm())"
    @save-key="afterCredentialChange(settings.saveCredential($event))"
    @test="afterCredentialChange(settings.testCredential($event))"
    @clear-override="afterCredentialChange(settings.clearLlmOverride())"
    @goto-source="openSourceSection($event)"
    @goto-keys="openKeysSection()"
    @focus-done="settings.focus = null"
  />
</template>
