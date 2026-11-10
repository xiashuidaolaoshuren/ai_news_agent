<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import type { RefVm } from '@/vm/types'

defineProps<{
  refVm: RefVm
  /** When true, the remove control is shown (composer). */
  removable?: boolean
  /** `composer-ref-chip` | `message-ref-chip` */
  odId: 'composer-ref-chip' | 'message-ref-chip'
}>()

defineEmits<{ remove: [] }>()
</script>

<template>
  <span class="chip ref-chip" :data-od-id="odId">
    <b>↳ d{{ refVm.digestId }} #{{ refVm.rank }}</b>
    <span class="t">{{ refVm.title }}</span>
    <button
      v-if="removable === true"
      type="button"
      class="icon-btn"
      :aria-label="`Remove reference to d${refVm.digestId} #${refVm.rank}`"
      @click="$emit('remove')"
    >
      <AppIcon name="close" />
    </button>
  </span>
</template>
