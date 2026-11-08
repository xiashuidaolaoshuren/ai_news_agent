<script setup lang="ts">
import { nextTick, onMounted, useTemplateRef, watch } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import KeysPanel from '@/components/settings/KeysPanel.vue'
import SourceSettings from '@/components/settings/SourceSettings.vue'
import type { KeyDraftKey, KeysVm } from '@/vm/settings'
import type { OutputLanguage } from '@/stores/settings'
import type { SourceProfileVm } from '@/vm/settings'

export interface SettingsDialogVm {
  open: boolean
  tab: 'sources' | 'keys'
  language: OutputLanguage
  profiles: SourceProfileVm[]
  fieldErrors: Record<string, string>
  saved: boolean
  loadError: string | null
  focus: string | null
  keys: KeysVm
}

const props = defineProps<{ vm: SettingsDialogVm }>()

const emit = defineEmits<{
  close: []
  save: []
  retry: []
  setTab: [tab: 'sources' | 'keys']
  updateLanguage: [language: OutputLanguage]
  updateProfile: [profile: SourceProfileVm]
  updateKeysDraft: [key: KeyDraftKey, value: string]
  saveLlm: []
  saveKey: [key: KeyDraftKey]
  test: [name: string]
  clearOverride: []
  gotoSource: [name: string]
  gotoKeys: []
  /** The dialog consumed the requested section, so the caller can clear it. */
  focusDone: []
}>()

const dialog = useTemplateRef<HTMLElement>('dialog')

/**
 * The prototype puts focus back on the Settings button when the dialog closes.
 * Remember what held focus as it opened, and restore it on close.
 */
let opener: HTMLElement | null = null

watch(
  () => props.vm.open,
  async (open) => {
    if (open) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      return
    }
    const target = opener
    opener = null
    if (target === null) {
      return
    }
    // The shell behind the dialog is inert while it is open; wait for that to lift
    // or the browser refuses the focus call.
    await nextTick()
    if (document.contains(target)) {
      target.focus({ preventScroll: true })
    }
  },
  { immediate: true },
)

/**
 * Scroll to the section a gear or a Keys link asked for, flash it, and put the
 * caret in it. The prototype drops `st.focus` once it has done so.
 */
async function settleFocus(): Promise<void> {
  if (!props.vm.open) {
    return
  }
  await nextTick()
  const root = dialog.value
  if (root === null) {
    return
  }
  const name = props.vm.focus
  if (name === null) {
    // Land on the active tab when the dialog opened on its own. A click inside
    // already holds focus, so switching tabs does not steal it back.
    if (!root.contains(document.activeElement)) {
      root.querySelector<HTMLElement>(`#tab-${props.vm.tab}`)?.focus({ preventScroll: true })
    }
    return
  }
  const onSources = props.vm.tab === 'sources'
  const target = onSources
    ? root.querySelector<HTMLElement>(`#set-${name}`)
    : root.querySelector<HTMLElement>(`[data-od-id="key-row-${name}"]`)
  // The profiles load after the dialog opens; a later watch run retries.
  if (target === null) {
    return
  }
  const body = root.querySelector<HTMLElement>('.modal-body')
  if (body !== null) {
    body.scrollTop += target.getBoundingClientRect().top - body.getBoundingClientRect().top - 16
  }
  target.classList.add('hl')
  const warning = onSources && name === 'github' ? root.querySelector<HTMLElement>('#gh-auth') : null
  const control =
    (onSources ? warning : null) ??
    (onSources
      ? target.querySelector<HTMLElement>('input, button')
      : target.querySelector<HTMLElement>(`#key-${name}`))
  control?.focus({ preventScroll: true })
  emit('focusDone')
}

watch(
  () => [props.vm.open, props.vm.tab, props.vm.focus, props.vm.profiles.length] as const,
  () => {
    void settleFocus()
  },
  { flush: 'post' },
)

onMounted(() => {
  void settleFocus()
})

/**
 * Escape closes the dialog, unless focus is in a field the user is still
 * editing: the prototype treats the dialog as the top of its Escape chain.
 */
function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') {
    return
  }
  event.stopPropagation()
  emit('close')
}

const TABS = ['sources', 'keys'] as const

/**
 * A tablist moves with the arrow keys: the prototype switches to the other tab
 * and puts focus on it, so the roving tabindex is not a dead end.
 */
async function onTabKeydown(event: KeyboardEvent): Promise<void> {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') {
    return
  }
  event.preventDefault()
  const index = TABS.indexOf(props.vm.tab)
  const step = event.key === 'ArrowRight' ? 1 : -1
  const next = TABS[(index + step + TABS.length) % TABS.length]
  emit('setTab', next)
  await nextTick()
  dialog.value?.querySelector<HTMLElement>(`#tab-${next}`)?.focus({ preventScroll: true })
}
</script>

<template>
  <div v-if="vm.open" class="modal-wrap" @click.self="$emit('close')" @keydown="onKeydown">
    <div
      ref="dialog"
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="set-title"
      data-od-id="settings-dialog"
    >
      <div class="hist-head">
        <AppIcon name="gear" />
        <h2 id="set-title">Settings</h2>
        <span class="muted">Applies to new requests</span>
        <span class="grow" />
        <button type="button" class="icon-btn" aria-label="Close settings" @click="$emit('close')">
          <AppIcon name="close" />
        </button>
      </div>
      <div class="tabs" role="tablist" aria-label="Settings sections" @keydown="onTabKeydown">
        <button
          v-for="tab in (['sources', 'keys'] as const)"
          :id="`tab-${tab}`"
          :key="tab"
          type="button"
          class="tab"
          role="tab"
          :data-od-id="`settings-tab-${tab}`"
          :aria-selected="vm.tab === tab"
          aria-controls="set-panel"
          :tabindex="vm.tab === tab ? 0 : -1"
          @click="$emit('setTab', tab)"
        >
          {{ tab === 'sources' ? 'Sources' : 'Keys' }}
        </button>
      </div>
      <div
        id="set-panel"
        class="modal-body"
        role="tabpanel"
        :aria-labelledby="`tab-${vm.tab}`"
      >
        <div v-if="vm.loadError" class="alert alert-danger" role="alert">
          <AppIcon name="alert" />
          <p>{{ vm.loadError }}</p>
          <button type="button" class="btn btn-sm act" @click="$emit('retry')">Retry</button>
        </div>
        <SourceSettings
          v-if="vm.tab === 'sources'"
          :language="vm.language"
          :profiles="vm.profiles"
          :field-errors="vm.fieldErrors"
          :github-auth-error="vm.keys.githubAuthError"
          @update-language="$emit('updateLanguage', $event)"
          @update-profile="$emit('updateProfile', $event)"
          @goto-keys="$emit('gotoKeys')"
        />
        <KeysPanel
          v-else
          :vm="vm.keys"
          @update-draft="(key, value) => $emit('updateKeysDraft', key, value)"
          @save-llm="$emit('saveLlm')"
          @save-key="$emit('saveKey', $event)"
          @test="$emit('test', $event)"
          @clear-override="$emit('clearOverride')"
          @goto-source="$emit('gotoSource', $event)"
        />
      </div>
      <div v-if="vm.tab === 'sources'" class="modal-foot">
        <span class="help" role="status">
          {{ vm.saved ? 'Saved. New requests use these settings.' : '' }}
        </span>
        <span class="grow" />
        <button type="button" class="btn btn-ghost" @click="$emit('close')">Cancel</button>
        <button
          type="button"
          class="btn btn-primary"
          data-od-id="save-sources"
          @click="$emit('save')"
        >
          Save sources
        </button>
      </div>
      <div v-else class="modal-foot">
        <span class="help">Secrets are never shown after saving.</span>
        <span class="grow" />
        <button type="button" class="btn" @click="$emit('close')">Done</button>
      </div>
    </div>
  </div>
</template>
