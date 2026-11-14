<script setup lang="ts">
import { computed } from 'vue'

import type { DigestVm, RefVm, SectionVm } from '@/vm'
import type { RepeatVm } from '@/vm/session'
import { riseStyle } from '@/lib/motion'

import AppIcon from '@/components/ui/AppIcon.vue'
import DigestSection from '@/components/thread/DigestSection.vue'
import { formatDigestWhen } from '@/components/thread/format'
import { t, type LabelKey } from '@/i18n/labels'

const props = defineProps<{ digest: DigestVm; animate?: boolean; repeat?: RepeatVm | null }>()

const emit = defineEmits<{
  deepdive: [ref: RefVm]
  ask: [ref: RefVm]
  'goto-related': [ref: RefVm]
  repeat: [repeat: RepeatVm]
  openSettings: [name: string]
}>()

/** Connectors with a Settings section; every source except hidden Bilibili. */
const SETTINGS_SOURCES = new Set(['juya', 'huggingface', 'github', 'zhihu', 'openrouter'])

/**
 * The prototype puts a settings button on a warning only for a connector that
 * has a section, so the button and `settings.focus` agree.
 */
function settingsSource(source: string): string | null {
  return SETTINGS_SOURCES.has(source) ? source : null
}

function isWindowNotice(warning: DigestVm['warnings'][number]): boolean {
  return warning.source === 'openrouter' && warning.code === 'window_widened'
}

const when = computed(() =>
  formatDigestWhen(props.digest.generatedAt, props.digest.lang === 'zh-CN' ? 'zh-CN' : 'en-US'),
)

/** Chrome label in the digest's language. */
function tr(key: LabelKey, vars?: Record<string, string | number>): string {
  return t(props.digest.lang, key, vars)
}

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
      <h2>{{ tr('digestHead') }}</h2>
      <span v-if="digest.ref" class="ref">{{ digest.ref }}</span>
      <span class="digest-meta">{{ when ? `${when} · ` : '' }}{{ tr('digestMeta', { items: digest.itemCount, returned: digest.sourcesReturned, total: digest.sourcesTotal }) }}</span>
    </div>

    <div
      v-for="(warning, index) in digest.warnings"
      :key="`${warning.source}:${warning.code}`"
      class="alert"
      :class="[isWindowNotice(warning) ? 'alert-info' : 'alert-warn', { rise: props.animate === true }]"
      :style="warningStyle(index)"
      :role="isWindowNotice(warning) ? 'status' : 'alert'"
      :data-od-id="`connector-warning-${warning.source.toLowerCase()}`"
    >
      <AppIcon :name="isWindowNotice(warning) ? 'info' : 'alert'" />
      <p><b>{{ warning.label }}{{ isWindowNotice(warning) ? tr('windowPrefix') : tr('connectorSuffix') }}</b> {{ warning.message }}</p>
      <button
        v-if="!isWindowNotice(warning) && settingsSource(warning.source) !== null"
        type="button"
        class="btn btn-sm act"
        @click="emit('openSettings', warning.source)"
      >
        {{ tr('settingsFor', { label: warning.label }) }}
      </button>
    </div>

    <DigestSection
      v-for="(section, index) in digest.sections"
      :key="`${section.kind}:${section.rangeStart}`"
      :section="section"
      :digest-id="digest.digestId ?? -1"
      :animate="props.animate === true"
      :start-index="sectionStarts[index] ?? 0"
      @deepdive="emit('deepdive', $event)"
      @ask="emit('ask', $event)"
      @goto-related="emit('goto-related', $event)"
    />

    <div v-if="props.repeat" class="digest-foot" data-od-id="digest-run-again">
      <button
        type="button"
        class="btn btn-sm"
        :aria-describedby="`again-${digest.ref ?? 'digest'}`"
        @click="emit('repeat', props.repeat)"
      >
        <AppIcon name="refresh" />{{ tr('runAgain') }}
      </button>
      <p class="help" :id="`again-${digest.ref ?? 'digest'}`">
        {{ tr('repeatHelp', { ref: digest.ref ?? '', summary: props.repeat.summary }) }}
      </p>
    </div>
  </div>
</template>
