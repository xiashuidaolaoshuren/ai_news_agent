<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import AvatarTile from '@/components/thread/AvatarTile.vue'
import EntryParagraphs from '@/components/thread/EntryParagraphs.vue'
import SourceTag from '@/components/thread/SourceTag.vue'
import { riseStyle } from '@/lib/motion'
import { hostOf } from '@/vm'
import type { EntryVm } from '@/vm'

const props = defineProps<{
  entry: EntryVm
  /** Stagger position when this row arrived live; null keeps it still. */
  rise?: number | null
}>()

const emit = defineEmits<{ followup: [title: string] }>()

/** Juya stories link to the original story, everything else to the entry url. */
const externalUrl = computed(() => props.entry.juya?.originalUrl ?? props.entry.url)
const externalHost = computed(() => hostOf(externalUrl.value))
const sourceText = computed(
  () => props.entry.juya?.topic ?? props.entry.meta ?? props.entry.sourceName,
)

/** True while this row holds a stagger position, which is what `.rise` needs. */
const rises = computed(() => props.rise !== null && props.rise !== undefined)

/** Juya stories get their own labels and a compact, expandable body. */
const isJuya = computed(() => props.entry.juya !== undefined)
const expanded = ref(false)
const background = computed(() => props.entry.juya?.background ?? null)

/** Character budgets for the collapsed view, close to three and two lines. */
const COLLAPSED_SUMMARY_MAX = 120
const COLLAPSED_WHY_MAX = 90

const labels = computed(() =>
  isJuya.value
    ? { summary: '摘要', why: '为什么重要', background: '背景知识' }
    : { summary: 'Summary', why: 'Why it matters', background: '' },
)

/**
 * Show the disclosure whenever expanding reveals something: background text,
 * a second paragraph, or prose past the collapsed character budget.
 */
const showsDisclosure = computed(() => {
  if (!isJuya.value) {
    return false
  }
  if (background.value !== null) {
    return true
  }
  const summary = props.entry.summary ?? ''
  const why = props.entry.whyItMatters ?? ''
  return (
    summary.length > COLLAPSED_SUMMARY_MAX ||
    why.length > COLLAPSED_WHY_MAX ||
    summary.includes('\n\n') ||
    why.includes('\n\n')
  )
})

const showsBackground = computed(
  () => isJuya.value && expanded.value && background.value !== null,
)
</script>

<template>
  <li class="entry" :class="{ rise: rises }" :style="riseStyle(props.rise)">
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

      <dl
        v-if="props.entry.summary || props.entry.whyItMatters || showsBackground"
        class="entry-body"
        :class="{ 'entry-body-juya': isJuya }"
      >
        <div v-if="props.entry.summary">
          <dt>{{ labels.summary }}</dt>
          <dd :class="{ 'clamp-summary': isJuya && !expanded }">
            <EntryParagraphs v-if="isJuya" :text="props.entry.summary" />
            <template v-else>{{ props.entry.summary }}</template>
          </dd>
        </div>
        <div v-if="props.entry.whyItMatters">
          <dt>{{ labels.why }}</dt>
          <dd :class="{ 'clamp-why': isJuya && !expanded }">
            <EntryParagraphs v-if="isJuya" :text="props.entry.whyItMatters" />
            <template v-else>{{ props.entry.whyItMatters }}</template>
          </dd>
        </div>
        <div v-if="showsBackground">
          <dt>{{ labels.background }}</dt>
          <dd><EntryParagraphs :text="background" /></dd>
        </div>
      </dl>

      <p v-if="props.entry.caveat" class="entry-caveat">{{ props.entry.caveat }}</p>

      <div v-if="showsDisclosure" class="entry-details">
        <button
          type="button"
          class="link-btn entry-toggle"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          {{ expanded ? '收起详情' : '展开详情' }}
        </button>
      </div>

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
