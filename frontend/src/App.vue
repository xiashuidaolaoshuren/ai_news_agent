<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { healthApiV1HealthGet } from '@/api/generated'
import { setupApiClient } from '@/api/setupClient'

setupApiClient()

const healthLine = ref('Loading API health…')
const errorLine = ref<string | null>(null)

onMounted(async () => {
  const { data, error } = await healthApiV1HealthGet()
  if (error) {
    errorLine.value = 'Health request failed'
    healthLine.value = ''
    return
  }
  const status = typeof data?.status === 'string' ? data.status : 'unknown'
  const fake = data?.fake === true
  healthLine.value = `API health: ${status} (fake=${fake})`
})
</script>

<template>
  <main class="p-6 font-sans text-sm text-foreground">
    <p v-if="errorLine" class="text-destructive">{{ errorLine }}</p>
    <p v-else>{{ healthLine }}</p>
  </main>
</template>
