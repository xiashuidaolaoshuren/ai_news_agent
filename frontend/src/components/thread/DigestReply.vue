<script setup lang="ts">
import { computed } from 'vue'

import type { DigestVm, SectionVm } from '@/vm'
import { riseStyle } from '@/lib/motion'

import AppIcon from '@/components/ui/AppIcon.vue'
import DigestSection from '@/components/thread/DigestSection.vue'
import { formatDigestWhen } from '@/components/thread/format'

const props = defineProps<{ digest: DigestVm; animate?: boolean }>()

const emit = defineEmits<{ followup: [title: string] }>()

const when = computed(() => formatDigestWhen(props.digest.generatedAt))

/** Rows one section staggers: its entries, or the stories of its Juya issues. */
function rowsIn(section: SectionVm): number {
  if (section.juyaIssues) {
    return section.juyaIssues.reduce((total, issue) => total + issue.stories.length, 0)
  }
  return section.entries.length
}

/**
 * The prototype's stagger counts across the whole digest in render order: the
 * head first, then the connector warnings, then every entry or table row.
 */
const sectionStarts = computed<number[]>(() => {
  let next = 1 + props.digest.warnings.length
  return props.digest.sections.map((section) => {
    const start = next
    next += rowsIn(section)
    return start
  })
})

/** The head and the warnings take the first positions of that same count. */
function headStyle(): string | undefined {
  return props.animate === true ? riseStyle(0) : undefined
}

function warningStyle(index: number): string | undefined {
  return props.animate === true ? riseStyle(1 + index) : undefined
}
</script>

<template>
  <div class="digest-reply">
    <div class="digest-head" :class="{ rise: props.animate === true }" :style="headStyle()">
      <h2>Digest</h2>
      <span v-if="digest.ref" class="ref">{{ digest.ref }}</span>
      <span class="digest-meta">{{ when ? `${when} · ` : '' }}{{ digest.itemCount }} items · {{ digest.sourcesReturned }} of {{ digest.sourcesTotal }} sources returned results</span>
    </div>

    <div
      v-for="(warning, index) in digest.warnings"
      :key="`${warning.source}:${warning.code}`"
      class="alert alert-warn"
      :class="{ rise: props.animate === true }"
      :style="warningStyle(index)"
      role="alert"
    >
      <AppIcon name="alert" />
      <p><b>{{ warning.label }} connector:</b> {{ warning.message }}</p>
    </div>

    <DigestSection
      v-for="(section, index) in digest.sections"
      :key="`${section.kind}:${section.rangeStart}`"
      :section="section"
      :animate="props.animate === true"
      :start-index="sectionStarts[index] ?? 0"
      @followup="emit('followup', $event)"
    />
  </div>
</template>
