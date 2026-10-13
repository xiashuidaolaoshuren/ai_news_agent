<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import ReconnectBanner from '@/components/thread/ReconnectBanner.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import type { RunStepVm, RunVm } from '@/vm/run'

const props = defineProps<{ run: RunVm }>()

const paused = computed(
  () => props.run.reconnect !== null && !props.run.reconnect.ok,
)

/** Total items the finished sources returned, for the writing-phase sentence. */
const ranked = computed(() =>
  props.run.steps.reduce((total, step) => total + (step.count ?? 0), 0),
)

/** Prototype step icons: done, running, queued, timed out. */
const STEP_ICONS = {
  done: 'check',
  run: 'load',
  warn: 'alert',
  queued: 'dot',
} as const

function stepCopy(step: RunStepVm): string {
  if (step.status === 'done') {
    return `${step.count ?? 0} items`
  }
  if (step.status === 'run') {
    return paused.value ? 'Paused while reconnecting' : 'Fetching…'
  }
  if (step.status === 'warn') {
    return 'Timed out'
  }
  return 'Queued'
}
</script>

<template>
  <div class="run" data-od-id="streaming-progress" aria-live="polite">
    <div class="run-head">
      <AppIcon :name="paused ? 'refresh' : 'load'" class="spin" />
      <span>{{ props.run.headline }}</span>
      <span v-if="props.run.startedAt" class="muted mono">started {{ props.run.startedAt }}</span>
    </div>

    <ReconnectBanner v-if="props.run.reconnect" :reconnect="props.run.reconnect" />

    <div
      class="segbar"
      :class="{ paused }"
      role="progressbar"
      :aria-valuenow="props.run.finished"
      aria-valuemin="0"
      :aria-valuemax="props.run.total"
      aria-label="Sources finished"
    >
      <span
        v-for="(step, index) in props.run.steps"
        :key="`${step.source}:${index}`"
        :class="`s-${step.status}`"
      ><i /></span>
    </div>

    <ol v-if="props.run.structured" class="steps">
      <li
        v-for="(step, index) in props.run.steps"
        :key="`${step.source}:${index}`"
        :class="`st-${step.status}`"
      >
        <AppIcon :name="STEP_ICONS[step.status]" :class="{ spin: step.status === 'run' }" />
        <SourceLogo v-if="step.kind" :kind="step.kind" />
        <span>{{ step.label }}</span>
        <span class="st">{{ stepCopy(step) }}</span>
        <span class="mono muted">{{ step.at ?? '' }}</span>
      </li>
    </ol>
    <p v-else class="stream-text">{{ props.run.fallbackStage ?? '' }}</p>

    <template v-if="props.run.phase === 'writing'">
      <p class="stream-text">
        Ranking {{ ranked }} items and drafting summaries<span class="caret" />
      </p>
      <div class="writing">
        <div class="line" style="width: 92%" />
        <div class="line" style="width: 78%" />
        <div class="line" style="width: 64%" />
      </div>
    </template>
  </div>
</template>
