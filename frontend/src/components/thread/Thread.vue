<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

import DigestReply from '@/components/thread/DigestReply.vue'
import EmptyConversation from '@/components/thread/EmptyConversation.vue'
import HoverPreview from '@/components/thread/HoverPreview.vue'
import MarkdownReply from '@/components/thread/MarkdownReply.vue'
import { formatClock } from '@/components/thread/format'
import { installHoverPreviewListeners } from '@/lib/useHoverPreview'
import type { MessageVm } from '@/vm'

const props = defineProps<{ messages: MessageVm[] }>()

const emit = defineEmits<{ followup: [title: string]; suggest: [text: string] }>()

const thread = ref<HTMLElement | null>(null)
let uninstall: (() => void) | null = null

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
        v-if="props.messages.length === 0"
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
          <MarkdownReply v-else :text="message.text" />
        </div>
      </template>
    </div>
    <HoverPreview />
  </div>
</template>
