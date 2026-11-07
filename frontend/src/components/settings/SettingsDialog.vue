<script setup lang="ts">
import SourceSettings from '@/components/settings/SourceSettings.vue'
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
}

defineProps<{ vm: SettingsDialogVm }>()

defineEmits<{
  close: []
  save: []
  retry: []
  updateLanguage: [language: OutputLanguage]
  updateProfile: [profile: SourceProfileVm]
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
        <h2 id="set-title">Settings</h2>
        <span>Applies to new requests</span>
      </div>
      <div class="tabs" role="tablist">
        <button
          type="button"
          class="tab"
          role="tab"
          data-od-id="settings-tab-sources"
          :aria-selected="vm.tab === 'sources'"
        >
          Sources
        </button>
      </div>
      <div class="modal-body" role="tabpanel">
        <div v-if="vm.loadError" class="alert alert-danger" role="alert">
          <p>{{ vm.loadError }}</p>
          <button type="button" @click="$emit('retry')">Retry</button>
        </div>
        <SourceSettings
          :language="vm.language"
          :profiles="vm.profiles"
          :field-errors="vm.fieldErrors"
          @update-language="$emit('updateLanguage', $event)"
          @update-profile="$emit('updateProfile', $event)"
        />
      </div>
      <div class="modal-foot">
        <span v-if="vm.saved" role="status">Saved. New requests use these settings.</span>
        <button type="button" @click="$emit('close')">Cancel</button>
        <button type="button" data-od-id="save-sources" @click="$emit('save')">Save sources</button>
      </div>
    </div>
  </div>
</template>
