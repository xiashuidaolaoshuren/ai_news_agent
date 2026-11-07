<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'

defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="alert alert-danger" role="alert" data-od-id="conversation-load-failed">
    <AppIcon name="alert" />
    <p>
      <b>Couldn’t load this conversation.</b> Its saved messages weren’t changed.
    </p>
    <button type="button" class="btn btn-sm act" data-od-id="retry-load" @click="$emit('retry')">
      <AppIcon name="refresh" />Retry
    </button>
  </div>
</template>
