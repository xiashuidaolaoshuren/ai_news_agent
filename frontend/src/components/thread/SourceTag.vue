<script setup lang="ts">
import SourceLogo from '@/components/thread/SourceLogo.vue'
import { sourceLabel } from '@/vm'
import type { EntryKind } from '@/vm'

const props = defineProps<{ kind: EntryKind }>()
</script>

<template>
  <span class="src-tag"><SourceLogo :kind="props.kind" />{{ sourceLabel(props.kind) }}</span>
</template>
