<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import type { ReconnectVm } from '@/vm/run'

const props = defineProps<{ reconnect: ReconnectVm; leaving?: boolean }>()

const nextCopy = computed(() =>
  props.reconnect.nextSeconds !== null && props.reconnect.nextSeconds > 0
    ? `next try in ${props.reconnect.nextSeconds}s`
    : 'trying now…',
)

const droppedCopy = computed(() =>
  props.reconnect.droppedAt === null
    ? 'Stream dropped.'
    : `Stream dropped at ${props.reconnect.droppedAt}.`,
)
</script>

<template>
  <div class="rc-wrap collapse" :class="{ shut: props.leaving === true }">
    <div>
      <div v-if="props.reconnect.ok" class="alert alert-ok" role="status">
        <AppIcon name="check" />
        <p><b>Reconnected.</b> Progress was kept and the request continues.</p>
      </div>
      <div v-else class="alert alert-info" role="status" data-od-id="reconnecting-banner">
        <AppIcon name="refresh" class="spin" />
        <p>
          <b>{{ droppedCopy }}</b>
          Reconnecting to the running request · attempt {{ props.reconnect.attempt }} of
          {{ props.reconnect.max }} · {{ nextCopy }}
        </p>
      </div>
    </div>
  </div>
</template>
