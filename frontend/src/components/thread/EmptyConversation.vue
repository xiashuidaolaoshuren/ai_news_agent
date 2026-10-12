<script setup lang="ts">
import AppIcon from '@/components/thread/AppIcon.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import type { EntryKind } from '@/vm'

const emit = defineEmits<{ suggest: [text: string] }>()

/** Source order of the prototype's orbit. */
const ORBIT: EntryKind[] = ['juya', 'huggingface', 'github', 'zhihu', 'bilibili']

const SUGGESTIONS = [
  'What shipped in open-weight models this week?',
  'Trending agent tooling on GitHub, 5 per source',
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
      Choose sources below, then ask about a topic or simply what’s new. Juya is on by default; the
      other sources are opt-in.
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
