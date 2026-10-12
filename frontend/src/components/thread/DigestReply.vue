<script setup lang="ts">
import { computed } from 'vue'

import type { DigestVm } from '@/vm'

import AppIcon from '@/components/ui/AppIcon.vue'
import DigestSection from '@/components/thread/DigestSection.vue'
import { formatDigestWhen } from '@/components/thread/format'

const props = defineProps<{ digest: DigestVm }>()

const emit = defineEmits<{ followup: [title: string] }>()

const when = computed(() => formatDigestWhen(props.digest.generatedAt))
</script>

<template>
  <div class="digest-reply">
    <div class="digest-head">
      <h2>Digest</h2>
      <span v-if="digest.ref" class="ref">{{ digest.ref }}</span>
      <span class="digest-meta">{{ when ? `${when} · ` : '' }}{{ digest.itemCount }} items · {{ digest.sourcesReturned }} of {{ digest.sourcesTotal }} sources returned results</span>
    </div>

    <div
      v-for="warning in digest.warnings"
      :key="`${warning.source}:${warning.code}`"
      class="alert alert-warn"
      role="alert"
    >
      <AppIcon name="alert" />
      <p><b>{{ warning.label }} connector:</b> {{ warning.message }}</p>
    </div>

    <DigestSection
      v-for="section in digest.sections"
      :key="`${section.kind}:${section.rangeStart}`"
      :section="section"
      @followup="emit('followup', $event)"
    />
  </div>
</template>
