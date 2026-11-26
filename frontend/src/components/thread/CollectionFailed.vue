<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { sourceLabel } from '@/vm/digest'
import type { CollectionVm, RepeatVm } from '@/vm/session'

const props = defineProps<{
  collection: CollectionVm
  repeat: RepeatVm | null
}>()

const emit = defineEmits<{ repeat: [payload: RepeatVm] }>()

const source = props.collection.failedSource
const label = source === null ? 'a source' : sourceLabel(source)

/** The reason as its own sentence: connector messages vary in whether they end with a stop. */
const reasonText = computed(() => {
  const reason = (props.collection.reason ?? '').trim()
  if (reason === '' || /[.!?。]$/.test(reason)) {
    return reason
  }
  return `${reason}.`
})

function retry(): void {
  if (props.repeat !== null) {
    emit('repeat', props.repeat)
  }
}
</script>

<template>
  <div class="alert alert-danger" role="alert" data-od-id="collection-failed">
    <AppIcon name="alert" />
    <p>
      <b>Couldn’t collect from {{ label }}.</b>
      {{ reasonText }} No stories were checked, so this isn’t a “no news” result.
    </p>
    <button
      v-if="props.repeat"
      type="button"
      class="btn btn-sm act"
      data-od-id="retry-collection"
      @click="retry"
    >
      <AppIcon name="refresh" />Retry
    </button>
  </div>
</template>
