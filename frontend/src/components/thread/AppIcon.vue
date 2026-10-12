<script setup lang="ts">
import { AlertTriangle, ExternalLink, Reply, Sparkles } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name: 'alert' | 'ext' | 'reply' | 'spark' }>()

const ICONS = {
  alert: AlertTriangle,
  ext: ExternalLink,
  reply: Reply,
  spark: Sparkles,
} as const

const icon = computed(() => ICONS[props.name])
</script>

<template>
  <component :is="icon" class="ic" :size="16" :stroke-width="1.75" aria-hidden="true" />
</template>
