<script setup lang="ts">
import { computed } from 'vue'

import SourceLogo from '@/components/thread/SourceLogo.vue'
import { sourceLabel } from '@/vm/digest'
import type { CollectionVm, RepeatVm } from '@/vm/session'
import type { EntryKind } from '@/vm/types'

const props = defineProps<{
  collection: CollectionVm
  repeat: RepeatVm | null
  /** Sources the user can try instead of the ones already checked. */
  catalog: { name: string; label: string; kind: EntryKind | null }[]
}>()

const emit = defineEmits<{
  repeat: [payload: RepeatVm & { replaceSource: string }]
}>()

const MAX_SUGGESTIONS = 3

const checked = computed(() => new Set(props.collection.sources))

const suggestions = computed(() =>
  props.catalog
    .filter((source) => source.kind !== null && !checked.value.has(source.kind))
    .slice(0, MAX_SUGGESTIONS),
)

const checkedLabels = computed(() =>
  props.collection.sources.map((kind) => sourceLabel(kind)).join(' and '),
)

function trySource(name: string): void {
  if (props.repeat === null) {
    return
  }
  emit('repeat', {
    ...props.repeat,
    text: props.repeat.text,
    replaceSource: name,
  })
}
</script>

<template>
  <section class="section" data-od-id="no-eligible-results">
    <div class="section-head">
      <span class="tile"><SourceLogo :kind="props.collection.sources[0] ?? 'github'" /></span>
      <h3>No eligible results</h3>
      <span class="sub">{{ checkedLabels }}{{ props.collection.timeframe ? ` · ${props.collection.timeframe}` : '' }}</span>
    </div>
    <div class="set-body">
      <p style="margin: 0">
        {{ checkedLabels }} was checked, and none of its stories
        <template v-if="props.collection.timeframe"> from the {{ props.collection.timeframe }}</template>
        <template v-if="props.collection.topic">
          match <b>{{ props.collection.topic }}</b></template
        >.
      </p>
      <div v-if="suggestions.length > 0">
        <p class="help" style="margin-bottom: 8px">
          Try another source. It runs
          <template v-if="props.collection.topic"> <b>{{ props.collection.topic }}</b></template>
          <template v-if="props.collection.timeframe"> for the <b>{{ props.collection.timeframe }}</b></template>.
        </p>
        <div class="seg">
          <button
            v-for="source in suggestions"
            :key="source.name"
            type="button"
            class="btn btn-sm"
            :data-od-id="`try-${source.name}`"
            @click="trySource(source.name)"
          >
            <SourceLogo v-if="source.kind" :kind="source.kind" />Try {{ source.label }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
