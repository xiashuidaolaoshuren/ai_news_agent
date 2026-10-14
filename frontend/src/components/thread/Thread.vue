<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import CancelledReply from '@/components/thread/CancelledReply.vue'
import DigestReply from '@/components/thread/DigestReply.vue'
import EmptyConversation from '@/components/thread/EmptyConversation.vue'
import FailedReply from '@/components/thread/FailedReply.vue'
import HoverPreview from '@/components/thread/HoverPreview.vue'
import InterruptedReply from '@/components/thread/InterruptedReply.vue'
import MarkdownReply from '@/components/thread/MarkdownReply.vue'
import RunCard from '@/components/thread/RunCard.vue'
import { formatClock } from '@/components/thread/format'
import { installHoverPreviewListeners } from '@/lib/useHoverPreview'
import { prefersReducedMotion } from '@/lib/motion'
import { PENDING_MESSAGE_ID } from '@/stores/thread'
import type { MessageVm, RequestStateVm } from '@/vm'
import type { CancelledVm, RunVm } from '@/vm/run'

const props = defineProps<{
  messages: MessageVm[]
  /** Rows the last reload brought in, which are the only transcript rows that animate. */
  freshIds?: number[]
  run?: RunVm | null
  cancelled?: CancelledVm | null
  alert?: RequestStateVm | null
}>()

const emit = defineEmits<{
  followup: [title: string]
  suggest: [text: string]
  runAgain: []
}>()

/**
 * A cancelled reply loaded from the transcript carries no live source counts and
 * no client clock, so only its copy is known.
 */
const PERSISTED_CANCELLED: CancelledVm = {
  mode: 'digest',
  at: null,
  done: null,
  total: null,
}

/** How long the swap tween may run before its inline styles are dropped anyway. */
const SWAP_SETTLE_MS = 400

const thread = ref<HTMLElement | null>(null)
const liveSlot = ref<HTMLElement | null>(null)
let uninstall: (() => void) | null = null
let swapTimer: number | null = null
let swapFrom: number | null = null

/** The run label shows the `HH:MM` clock, while the card head carries the seconds. */
const runClock = computed(() => props.run?.startedAt?.slice(0, 5) ?? '')

/** A live arrival animates; a row that was already in the transcript does not. */
function isFresh(message: MessageVm): boolean {
  return props.freshIds?.includes(message.id) ?? false
}

/**
 * The cancelled alert replaces the run card in the same slot. The prototype
 * tweens the block from the old height to the new one so the swap does not jump.
 */
function playSwapTween(): void {
  const element = liveSlot.value
  const from = swapFrom
  swapFrom = null
  if (element === null || from === null || from === 0 || prefersReducedMotion()) {
    return
  }
  const to = element.offsetHeight
  if (to === from) {
    return
  }
  const clear = (): void => {
    if (swapTimer !== null) {
      window.clearTimeout(swapTimer)
      swapTimer = null
    }
    element.style.cssText = ''
  }
  element.style.height = `${from}px`
  element.style.overflow = 'hidden'
  // Read back so the starting height is committed before the transition begins.
  void element.offsetHeight
  element.style.transition = 'height var(--d3) var(--ease)'
  element.style.height = `${to}px`
  element.addEventListener('transitionend', clear, { once: true })
  swapTimer = window.setTimeout(clear, SWAP_SETTLE_MS)
}

watch(
  () => props.cancelled !== null,
  (cancelled) => {
    if (!cancelled) {
      return
    }
    swapFrom = liveSlot.value?.offsetHeight ?? null
    void nextTick(playSwapTween)
  },
)

onMounted(() => {
  if (thread.value !== null) {
    uninstall = installHoverPreviewListeners(thread.value)
  }
})

onUnmounted(() => {
  uninstall?.()
  uninstall = null
  if (swapTimer !== null) {
    window.clearTimeout(swapTimer)
    swapTimer = null
  }
})
</script>

<template>
  <div ref="thread" class="thread">
    <div class="thread-inner">
      <EmptyConversation
        v-if="
          props.messages.length === 0 &&
          !props.run &&
          !props.cancelled &&
          !props.alert
        "
        @suggest="emit('suggest', $event)"
      />
      <template v-for="message in props.messages" :key="message.id">
        <div
          v-if="message.kind === 'user'"
          class="msg-user"
          :class="{ rise: message.id === PENDING_MESSAGE_ID }"
          data-od-id="user-message"
        >
          <div class="bubble">{{ message.text }}</div>
        </div>

        <div
          v-else
          class="msg-ai"
          :class="{ 'fade-in': isFresh(message) && message.kind !== 'digest' }"
          :data-od-id="message.kind === 'digest' ? 'digest-reply' : undefined"
        >
          <div class="ai-label">
            <b>Agent</b>
            <span v-if="formatClock(message.createdAt)" class="mono">{{
              formatClock(message.createdAt)
            }}</span>
          </div>
          <DigestReply
            v-if="message.kind === 'digest' && message.digest"
            :digest="message.digest"
            :animate="isFresh(message)"
            @followup="emit('followup', $event)"
          />
          <CancelledReply
            v-else-if="message.kind === 'cancelled'"
            :cancelled="PERSISTED_CANCELLED"
            @run-again="emit('runAgain')"
          />
          <MarkdownReply v-else :text="message.text" />
        </div>
      </template>

      <div
        v-if="props.alert || props.cancelled || props.run"
        ref="liveSlot"
        class="live-slot"
      >
        <div v-if="props.alert" class="msg-ai fade-in">
          <div class="ai-label">
            <b>Agent</b>
          </div>
          <FailedReply
            v-if="props.alert.kind === 'failed'"
            :state="props.alert"
            @run-again="emit('runAgain')"
          />
          <InterruptedReply v-else :state="props.alert" @run-again="emit('runAgain')" />
        </div>

        <div v-else-if="props.cancelled" class="msg-ai fade-in">
          <div class="ai-label">
            <b>Agent</b>
          </div>
          <CancelledReply :cancelled="props.cancelled" @run-again="emit('runAgain')" />
        </div>

        <template v-else-if="props.run">
          <div class="msg-ai fade-in">
            <div class="ai-label">
              <b>Agent</b>
              <span v-if="runClock" class="mono">{{ runClock }}</span>
            </div>
            <MarkdownReply
              v-if="props.run.mode === 'followup'"
              :text="props.run.streamText"
              streaming
            />
            <RunCard v-else :run="props.run" />
          </div>
        </template>
      </div>
    </div>
    <HoverPreview />
  </div>
</template>
