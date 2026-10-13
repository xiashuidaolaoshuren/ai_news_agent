<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

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
import type { MessageVm, RequestStateVm } from '@/vm'
import type { CancelledVm, RunVm } from '@/vm/run'

const props = defineProps<{
  messages: MessageVm[]
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

const thread = ref<HTMLElement | null>(null)
let uninstall: (() => void) | null = null

/** The run label shows the `HH:MM` clock, while the card head carries the seconds. */
const runClock = computed(() => props.run?.startedAt?.slice(0, 5) ?? '')

onMounted(() => {
  if (thread.value !== null) {
    uninstall = installHoverPreviewListeners(thread.value)
  }
})

onUnmounted(() => {
  uninstall?.()
  uninstall = null
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
        <div v-if="message.kind === 'user'" class="msg-user" data-od-id="user-message">
          <div class="bubble">{{ message.text }}</div>
        </div>

        <div
          v-else
          class="msg-ai"
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

      <div v-if="props.alert" class="msg-ai">
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

      <div v-else-if="props.cancelled" class="msg-ai">
        <div class="ai-label">
          <b>Agent</b>
        </div>
        <CancelledReply :cancelled="props.cancelled" @run-again="emit('runAgain')" />
      </div>

      <template v-else-if="props.run">
        <div class="msg-ai">
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
    <HoverPreview />
  </div>
</template>
