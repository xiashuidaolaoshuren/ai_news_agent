<script setup lang="ts">
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

defineProps<{ vm: SettingsDialogVm }>()

defineEmits<{
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
}>()
</script>

<template>
  <div v-if="vm.open" class="modal-wrap">
    <div
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
      <div class="tabs" role="tablist" aria-label="Settings sections">
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
          <p>{{ vm.loadError }}</p>
          <button type="button" @click="$emit('retry')">Retry</button>
        </div>
        <SourceSettings
          v-if="vm.tab === 'sources'"
          :language="vm.language"
          :profiles="vm.profiles"
          :field-errors="vm.fieldErrors"
          @update-language="$emit('updateLanguage', $event)"
          @update-profile="$emit('updateProfile', $event)"
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
