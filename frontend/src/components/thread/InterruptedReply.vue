<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import type { RequestStateVm } from '@/vm'

const props = defineProps<{ state: RequestStateVm }>()

const emit = defineEmits<{ runAgain: [] }>()
</script>

<template>
  <div class="alert alert-info" role="alert" data-od-id="interrupted-reply">
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
  </div>
</template>
