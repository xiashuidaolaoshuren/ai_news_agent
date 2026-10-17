<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import type { CancelledVm } from '@/vm/run'

const props = defineProps<{ cancelled: CancelledVm }>()

const emit = defineEmits<{ runAgain: [] }>()

/** ` at 20:14:07` when the client saw the cancellation, empty otherwise. */
const at = computed(() => (props.cancelled.at === null ? '' : ` at ${props.cancelled.at}`))

/** Bold lead-in: the two prototype copies differ only in what was cancelled. */
const lead = computed(() =>
  props.cancelled.mode === 'text' ? `Reply cancelled${at.value}.` : `Request cancelled${at.value}.`,
)

/**
 * The counts are known only while the run is still in the client's hands; a
 * cancelled reply reloaded from the transcript has neither counts nor clock.
 */
const rest = computed(() => {
  if (props.cancelled.mode === 'text') {
    return ' The answer stopped before it finished.'
  }
  const { done, total } = props.cancelled
  const counts = done === null || total === null ? '' : ` ${done} of ${total} sources had finished.`
  return `${counts} No digest was added to this conversation.`
})
</script>

<template>
  <div class="alert alert-danger" role="status" data-od-id="cancelled-reply">
    <AppIcon name="ban" />
    <p><b>{{ lead }}</b>{{ rest }}</p>
    <button type="button" class="btn btn-sm act" @click="emit('runAgain')">
      <AppIcon name="refresh" />Run again
    </button>
  </div>
</template>
