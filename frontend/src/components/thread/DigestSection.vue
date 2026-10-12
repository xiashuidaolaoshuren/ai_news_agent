<script setup lang="ts">
import EntryRow from '@/components/thread/EntryRow.vue'
import HfTable from '@/components/thread/HfTable.vue'
import JuyaIssueCover from '@/components/thread/JuyaIssueCover.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import type { SectionVm } from '@/vm'

const props = defineProps<{ section: SectionVm }>()

const emit = defineEmits<{ followup: [title: string] }>()
</script>

<template>
  <section
    class="section"
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
            @followup="emit('followup', $event)"
          />
        </ol>
      </template>
    </template>

    <HfTable v-else-if="props.section.kind === 'huggingface'" :entries="props.section.entries" />

    <ol v-else class="entries">
      <EntryRow
        v-for="entry in props.section.entries"
        :key="entry.key"
        :entry="entry"
        @followup="emit('followup', $event)"
      />
    </ol>
  </section>
</template>
