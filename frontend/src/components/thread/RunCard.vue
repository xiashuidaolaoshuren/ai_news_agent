<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import ReconnectBanner from '@/components/thread/ReconnectBanner.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import type { RunStepVm, RunVm } from '@/vm/run'

const props = defineProps<{ run: RunVm }>()

/** How long a segment keeps its landing animation, matching `--d2`. */
const SEG_DONE_MS = 200

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

/**
 * The segment of the source that just finished, so it can land with `segdone`.
 * The prototype marks it as the running step turns done or warn and clears it on
 * the next render.
 */
const landed = ref<number | null>(null)
let landTimer: number | null = null

const statuses = computed(() => props.run.steps.map((step) => step.status))

watch(statuses, (next, previous) => {
  if (previous === undefined) {
    return
  }
  const index = next.findIndex(
    (status, position) =>
      status !== previous[position] && status !== 'run' && status !== 'queued',
  )
  // An unrelated redraw (a countdown tick, say) must not cut a landing short.
  if (index === -1) {
    return
  }
  if (landTimer !== null) {
    window.clearTimeout(landTimer)
    landTimer = null
  }
  landed.value = index
  landTimer = window.setTimeout(() => {
    landTimer = null
    landed.value = null
  }, SEG_DONE_MS)
})

onUnmounted(() => {
  if (landTimer !== null) {
    window.clearTimeout(landTimer)
    landTimer = null
  }
})

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

    <ReconnectBanner
      v-if="props.run.reconnect"
      :reconnect="props.run.reconnect"
      :leaving="props.run.reconnectLeaving"
    />

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
        :class="[`s-${step.status}`, { enter: landed === index }]"
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
