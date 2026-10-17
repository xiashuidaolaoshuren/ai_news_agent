<script setup lang="ts">
import { computed } from 'vue'

import EntryRow from '@/components/thread/EntryRow.vue'
import HfTable from '@/components/thread/HfTable.vue'
import JuyaIssueCover from '@/components/thread/JuyaIssueCover.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import type { EntryVm, SectionVm } from '@/vm'

const props = defineProps<{
  section: SectionVm
  /** Set when the section arrived live, so its rows and the section itself reveal. */
  animate?: boolean
  /** Where this section's rows start in the digest-wide stagger count. */
  startIndex?: number
}>()

const emit = defineEmits<{ followup: [title: string] }>()

/**
 * Stagger positions, counted in render order across the section. Juya stories are
 * numbered across their issues, since each issue's entries list is its own list.
 */
const offsets = computed<Map<string, number>>(() => {
  const map = new Map<string, number>()
  let next = props.startIndex ?? 0
  const add = (entry: EntryVm): void => {
    map.set(entry.key, next)
    next += 1
  }
  if (props.section.juyaIssues) {
    for (const issue of props.section.juyaIssues) {
      for (const story of issue.stories) {
        add(story)
      }
    }
  } else {
    for (const entry of props.section.entries) {
      add(entry)
    }
  }
  return map
})

function rowRise(entry: EntryVm): number | null {
  return props.animate === true ? (offsets.value.get(entry.key) ?? null) : null
}
</script>

<template>
  <section
    class="section"
    :class="{ 'fade-in': props.animate === true }"
    :data-od-id="`digest-section-${props.section.kind}`"
  >
    <div class="section-head">
      <span class="tile"><SourceLogo :kind="props.section.kind" /></span>
      <h3>{{ props.section.label }}</h3>
      <span class="sub"
        >{{ props.section.subtitle ? `${props.section.subtitle} · ` : ''
        }}{{ props.section.count }} item{{ props.section.count === 1 ? '' : 's' }}</span
      >
      <span class="grow"></span>
      <span class="mono muted">#{{ props.section.rangeStart }}–{{ props.section.rangeEnd }}</span>
    </div>

    <template v-if="props.section.juyaIssues">
      <template v-for="issue in props.section.juyaIssues" :key="issue.issueId">
        <JuyaIssueCover :issue="issue" />
        <ol class="entries">
          <EntryRow
            v-for="entry in issue.stories"
            :key="entry.key"
            :entry="entry"
            :rise="rowRise(entry)"
            @followup="emit('followup', $event)"
          />
        </ol>
      </template>
    </template>

    <HfTable
      v-else-if="props.section.kind === 'huggingface'"
      :entries="props.section.entries"
      :animate="props.animate === true"
      :start-index="props.startIndex ?? 0"
    />

    <ol v-else class="entries">
      <EntryRow
        v-for="entry in props.section.entries"
        :key="entry.key"
        :entry="entry"
        :rise="rowRise(entry)"
        @followup="emit('followup', $event)"
      />
    </ol>
  </section>
</template>
