<script setup lang="ts">
import { computed } from 'vue'

import { useSessionsStore } from '@/stores/sessions'

const store = useSessionsStore()

const dotClass = computed<string>(() => {
  if (!store.reachable) {
    return 'dot danger'
  }
  return store.fakeMode ? 'dot warn' : 'dot'
})
</script>

<template>
  <div class="sb-status" data-od-id="backend-status" role="status">
    <span :class="dotClass" />
    {{ store.statusCopy }}
  </div>
</template>

<style scoped>
.sb-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 8px;
  font-size: 11.5px;
  color: var(--muted);
}
</style>
