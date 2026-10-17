<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import type { SessionVm } from '@/vm'

const props = defineProps<{
  session: SessionVm
  active: boolean
  flashing: boolean
  renaming: boolean
}>()

const emit = defineEmits<{
  open: []
  requestRename: []
  submitRename: [title: string]
  cancelRename: []
  requestDelete: []
}>()

const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

// Focus and preselect the field as soon as the inline form appears, like the prototype.
watch(
  () => props.renaming,
  async (renaming) => {
    if (!renaming) {
      return
    }
    draft.value = props.session.isUntitled ? '' : props.session.title
    await nextTick()
    inputEl.value?.focus()
    inputEl.value?.select()
  },
  { immediate: true },
)

function onSubmit(): void {
  emit('submitRename', draft.value.trim())
}

function onFieldKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('cancelRename')
  }
}
</script>

<template>
  <div
    class="sess"
    :class="{
      active: props.active || props.renaming,
      'is-empty': props.session.isUntitled || props.session.digestCount === 0,
      flash: props.flashing,
    }"
    :data-flash="props.flashing ? 'true' : undefined"
  >
    <form
      v-if="props.renaming"
      class="sess-rename"
      @submit.prevent="onSubmit"
    >
      <label class="sr-only" :for="`rn-${props.session.id}`">Conversation name</label>
      <input
        :id="`rn-${props.session.id}`"
        ref="inputEl"
        v-model="draft"
        class="input"
        maxlength="80"
        @keydown="onFieldKeydown"
      />
      <button type="submit" class="icon-btn" aria-label="Save name">
        <AppIcon name="check" />
      </button>
      <button type="button" class="icon-btn" aria-label="Cancel rename" @click="emit('cancelRename')">
        <AppIcon name="close" />
      </button>
    </form>

    <template v-else>
      <button
        type="button"
        class="sess-main"
        :aria-current="props.active ? 'true' : undefined"
        @click="emit('open')"
      >
        <span class="sess-title">{{ props.session.title }}</span>
        <span class="sess-meta">
          {{ props.session.timeLabel
          }}<template v-if="props.session.digestCount === 0"> · no messages</template
          ><template v-else>
            · {{ props.session.digestCount }} digest{{
              props.session.digestCount === 1 ? '' : 's'
            }}
          </template>
          <template v-if="props.session.busy">
            · <span class="busy-dot"><AppIcon name="load" class="spin" />Running</span>
          </template>
        </span>
      </button>
      <div class="sess-actions">
        <button
          type="button"
          class="icon-btn"
          :aria-label="`Rename ${props.session.title}`"
          title="Rename"
          @click="emit('requestRename')"
        >
          <AppIcon name="pencil" />
        </button>
        <button
          type="button"
          class="icon-btn"
          :aria-label="`Delete ${props.session.title}`"
          title="Delete"
          @click="emit('requestDelete')"
        >
          <AppIcon name="trash" />
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sess {
  position: relative;
  border-radius: 7px;
  margin-bottom: 1px;
  transition: background-color var(--d1) var(--ease);
}

.sess:hover {
  background: var(--hover);
}

.sess.active {
  background: var(--active);
}

.sess-main {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 7px 64px 7px 10px;
  border-radius: 7px;
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

.sess.is-empty .sess-title {
  color: var(--muted);
  font-style: italic;
}

.sess-meta {
  font-size: 11.5px;
  color: var(--muted);
  display: flex;
  gap: 6px;
  align-items: center;
}

.busy-dot {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--info);
  font-weight: 500;
}

.busy-dot .ic {
  width: 12px;
  height: 12px;
}

.sess-actions {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  gap: 2px;
  opacity: 0;
}

.sess:hover .sess-actions,
.sess:focus-within .sess-actions,
.sess.active .sess-actions {
  opacity: 1;
}

.sess-rename {
  padding: 5px 6px;
  display: flex;
  gap: 4px;
}

.sess-rename .input {
  height: 30px;
}
</style>
