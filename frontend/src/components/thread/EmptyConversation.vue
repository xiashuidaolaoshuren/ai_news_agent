<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import { SHOW_BILIBILI } from '@/lib/features'
import type { EntryKind } from '@/vm'

const emit = defineEmits<{ suggest: [text: string] }>()

/** Source order of the prototype's orbit, which a hidden source leaves. */
const ALL_ORBIT: EntryKind[] = ['juya', 'huggingface', 'github', 'zhihu', 'bilibili']

const ORBIT: EntryKind[] = SHOW_BILIBILI
  ? ALL_ORBIT
  : ALL_ORBIT.filter((kind) => kind !== 'bilibili')

const SUGGESTIONS = [
  "Digest today's AI news",
  'What shipped in open-weight models this week?',
  'Trending agent tooling on GitHub this week',
  'Summarize the latest Juya AI 早报 for a beginner',
]
</script>

<template>
  <div class="empty" data-od-id="empty-conversation">
    <div class="orbit" aria-hidden="true">
      <span v-for="kind in ORBIT" :key="kind"><SourceLogo :kind="kind" /></span>
    </div>
    <h2>Start a digest</h2>
    <p>
      Ask in your own words. A question or a topic starts a digest and picks the sources for
      it; the sources below are your defaults, and naming a platform or count in a message
      applies to that run only.
    </p>
    <div class="suggest">
      <button
        v-for="(text, index) in SUGGESTIONS"
        :key="text"
        type="button"
        :data-od-id="`suggestion-${index + 1}`"
        @click="emit('suggest', text)"
      >
        <AppIcon name="spark" />{{ text }}
      </button>
    </div>
  </div>
</template>
