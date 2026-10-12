<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import AvatarTile from '@/components/thread/AvatarTile.vue'
import SourceTag from '@/components/thread/SourceTag.vue'
import { hostOf } from '@/vm'
import type { EntryVm } from '@/vm'

const props = defineProps<{ entry: EntryVm }>()

const emit = defineEmits<{ followup: [title: string] }>()

/** Juya stories link to the original story, everything else to the entry url. */
const externalUrl = computed(() => props.entry.juya?.originalUrl ?? props.entry.url)
const externalHost = computed(() => hostOf(externalUrl.value))
const sourceText = computed(
  () => props.entry.juya?.topic ?? props.entry.meta ?? props.entry.sourceName,
)
</script>

<template>
  <li class="entry">
    <div class="rank">#{{ props.entry.rank }}</div>
    <div>
      <h4>
        <AvatarTile :avatar="props.entry.avatar" />
        <a
          v-if="props.entry.url"
          :href="props.entry.url"
          target="_blank"
          rel="noopener"
          :data-preview="props.entry.previewUrl ?? undefined"
          >{{ props.entry.title }}</a
        >
        <span v-else>{{ props.entry.title }}</span>
      </h4>

      <div class="entry-src">
        <SourceTag :kind="props.entry.kind" />
        <span>{{ sourceText }}</span>
        <a
          v-if="externalHost && externalUrl"
          class="ext"
          :href="externalUrl"
          target="_blank"
          rel="noopener"
          >{{ externalHost }}<AppIcon name="ext" /></a
        >
      </div>

      <dl v-if="props.entry.summary || props.entry.whyItMatters" class="entry-body">
        <div v-if="props.entry.summary">
          <dt>Summary</dt>
          <dd>{{ props.entry.summary }}</dd>
        </div>
        <div v-if="props.entry.whyItMatters">
          <dt>Why it matters</dt>
          <dd>{{ props.entry.whyItMatters }}</dd>
        </div>
      </dl>

      <p v-if="props.entry.caveat" class="entry-caveat">{{ props.entry.caveat }}</p>

      <div class="entry-foot">
        <button
          type="button"
          class="link-btn"
          @click="emit('followup', props.entry.title)"
        >
          <AppIcon name="reply" />Ask a follow-up
        </button>
      </div>
    </div>
  </li>
</template>
