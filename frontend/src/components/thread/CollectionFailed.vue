<script setup lang="ts">
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
      {{ props.collection.reason }} No stories were checked, so this isn’t a “no news” result.
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
