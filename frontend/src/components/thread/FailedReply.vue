<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import type { RequestStateVm } from '@/vm'

const props = defineProps<{ state: RequestStateVm }>()

const emit = defineEmits<{ runAgain: []; retryPoll: [] }>()
</script>

<template>
  <div class="alert alert-danger" role="alert" data-od-id="failed-reply">
    <AppIcon name="alert" />
    <p><b>{{ props.state.message }}</b></p>
    <button
      v-if="props.state.canRunAgain"
      type="button"
      class="btn btn-sm act"
      @click="emit('runAgain')"
    >
      <AppIcon name="refresh" />Run again
    </button>
    <button
      v-if="props.state.canRetryPoll === true"
      type="button"
      class="btn btn-sm btn-ghost"
      @click="emit('retryPoll')"
    >
      <AppIcon name="refresh" />Keep polling
    </button>
  </div>
</template>
