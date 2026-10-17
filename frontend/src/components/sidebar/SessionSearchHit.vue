<script setup lang="ts">
import type { SessionHitVm } from '@/vm'

const props = defineProps<{ hit: SessionHitVm }>()

const emit = defineEmits<{ open: [] }>()

const KIND_LABEL: Record<SessionHitVm['matchKind'], string> = {
  title: 'in title',
  user: 'in your message',
  assistant: 'in the reply',
}
</script>

<template>
  <li class="hit">
    <button type="button" class="hit-main" :data-od-id="`search-hit-${props.hit.sessionId}`" @click="emit('open')">
      <span class="sess-title">{{ props.hit.title }}</span>
      <span class="sess-meta">
        <span class="kind">{{ KIND_LABEL[props.hit.matchKind] }}</span>
        <template v-if="props.hit.excerpt">· {{ props.hit.excerpt }}</template>
      </span>
    </button>
  </li>
</template>

<style scoped>
.hit {
  list-style: none;
}

.hit-main {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 7px 10px;
  border-radius: 7px;
  transition: background-color var(--d1) var(--ease);
}

.hit-main:hover {
  background: var(--hover);
}

.sess-title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.sess-meta {
  font-size: 11.5px;
  color: var(--muted);
  display: flex;
  gap: 6px;
  align-items: baseline;
  min-width: 0;
}

.kind {
  font-family: var(--font-mono);
  flex: none;
}
</style>
