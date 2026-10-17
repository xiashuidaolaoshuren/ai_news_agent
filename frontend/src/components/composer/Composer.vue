<script setup lang="ts">
import { computed, onMounted, onUnmounted, useTemplateRef } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import SourceLogo from '@/components/thread/SourceLogo.vue'
import type { ComposerVm } from '@/vm/composer'

const props = defineProps<{ vm: ComposerVm }>()

const emit = defineEmits<{
  send: []
  cancel: []
  updateText: [text: string]
  toggleSource: [name: string]
  commitCount: [raw: string]
  stepCount: [delta: number]
}>()

const dock = useTemplateRef<HTMLElement>('dock')
const input = useTemplateRef<HTMLTextAreaElement>('input')

const hasErrors = computed(() => Object.keys(props.vm.errors).length > 0)

/** Copy for the notice strip; a blocked send outranks the running notice. */
const NOTICE_COPY: Record<'running' | 'reconnecting', string> = {
  running: 'A request is running in this conversation. You can draft your next message.',
  reconnecting: 'Reconnecting to the running request…',
}

function errorList(): { id: string; message: string }[] {
  const { errors } = props.vm
  return [
    { id: 'err-text', message: errors.text },
    { id: 'err-sources', message: errors.sources },
    { id: 'err-n', message: errors.count },
    { id: 'err-send', message: errors.send },
    { id: 'err-prefs', message: errors.prefs },
  ].filter((item): item is { id: string; message: string } => item.message !== undefined)
}

/** Enter sends; Shift+Enter is a newline; a keypress during composition is the IME's. */
function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
    return
  }
  event.preventDefault()
  emit('send')
}

function onInput(event: Event): void {
  emit('updateText', (event.target as HTMLTextAreaElement).value)
}

function onCountInput(event: Event): void {
  emit('commitCount', (event.target as HTMLInputElement).value)
}

/**
 * The dock floats over the thread, so the prototype publishes its height as
 * `--dock-h` for the thread's bottom padding, and shifts left by the thread's
 * scrollbar. The observer watches both, as the prototype's does.
 */
let observer: ResizeObserver | null = null

function syncDock(): void {
  const element = dock.value
  const chat = element?.parentElement ?? null
  if (element === null || chat === null) {
    return
  }
  chat.style.setProperty('--dock-h', `${element.offsetHeight}px`)
  const thread = chat.querySelector<HTMLElement>('.thread')
  if (thread !== null) {
    element.style.right = `${thread.offsetWidth - thread.clientWidth}px`
  }
}

onMounted(() => {
  syncDock()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(syncDock)
    if (dock.value !== null) {
      observer.observe(dock.value)
    }
    const thread = dock.value?.parentElement?.querySelector('.thread')
    if (thread !== undefined && thread !== null) {
      observer.observe(thread)
    }
  }
})

onUnmounted(() => {
  observer?.disconnect()
  observer = null
})

defineExpose({
  focus(): void {
    input.value?.focus()
  },
})
</script>

<template>
  <div ref="dock" class="composer-dock">
    <form
      class="composer"
      :class="{ invalid: hasErrors }"
      novalidate
      data-od-id="composer"
      @submit.prevent="emit('send')"
    >
      <div
        v-if="props.vm.notice === 'blocked'"
        class="c-notice warn"
        role="alert"
        data-od-id="busy-blocked-notice"
      >
        <AppIcon name="alert" />Not sent. This conversation already has a request running — wait for
        the reply or cancel it.
      </div>
      <div
        v-else-if="props.vm.notice !== 'none'"
        class="c-notice info"
        role="status"
        data-od-id="busy-notice"
      >
        <AppIcon name="load" class="spin" />{{ NOTICE_COPY[props.vm.notice] }}
      </div>

      <label class="sr-only" for="msg">Message</label>
      <textarea
        id="msg"
        ref="input"
        rows="2"
        placeholder="Ask for a digest or a follow-up…"
        :value="props.vm.text"
        :aria-invalid="props.vm.errors.text !== undefined"
        :aria-describedby="props.vm.errors.text === undefined ? undefined : 'err-text'"
        data-od-id="composer-input"
        @input="onInput"
        @keydown="onKeydown"
      />

      <div class="c-bar">
        <fieldset
          class="sources"
          :aria-invalid="props.vm.errors.sources !== undefined"
          :aria-describedby="props.vm.errors.sources === undefined ? undefined : 'err-sources'"
          data-od-id="source-checkboxes"
        >
          <legend>Sources</legend>
          <label v-for="source in props.vm.sources" :key="source.name" class="src-chk">
            <input
              type="checkbox"
              :data-src="source.name"
              :checked="source.checked"
              :disabled="props.vm.busy"
              @change="emit('toggleSource', source.name)"
            />
            <span>
              <i class="box"><AppIcon name="check" /></i>
              <SourceLogo v-if="source.kind !== null" :kind="source.kind" />{{ source.label }}
            </span>
          </label>
        </fieldset>

        <div class="per">
          <label for="per-n">Per source</label>
          <div
            class="stepper"
            :class="{ err: props.vm.errors.count !== undefined }"
            data-od-id="items-per-source"
          >
            <button
              type="button"
              aria-label="Fewer items"
              :disabled="props.vm.busy"
              @click="emit('stepCount', -1)"
            >
              −
            </button>
            <input
              id="per-n"
              type="number"
              inputmode="numeric"
              min="1"
              max="20"
              :value="props.vm.count"
              :aria-invalid="props.vm.errors.count !== undefined"
              :aria-describedby="props.vm.errors.count === undefined ? undefined : 'err-n'"
              :disabled="props.vm.busy"
              @change="onCountInput"
            />
            <button
              type="button"
              aria-label="More items"
              :disabled="props.vm.busy"
              @click="emit('stepCount', 1)"
            >
              +
            </button>
          </div>
        </div>

        <div class="c-actions">
          <button
            v-if="props.vm.busy"
            type="button"
            class="btn btn-cancel"
            data-od-id="cancel-request"
            @click="emit('cancel')"
          >
            <AppIcon name="stop" />Cancel
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="props.vm.busy"
            data-od-id="send-button"
          >
            <AppIcon name="up" />Send
          </button>
        </div>
      </div>

      <div v-if="errorList().length > 0" class="c-errors" data-od-id="validation-errors">
        <p
          v-for="item in errorList()"
          :key="item.id"
          class="err-msg"
          :id="item.id"
        >
          <AppIcon name="alert" />{{ item.message }}
        </p>
      </div>
    </form>

    <div class="c-hint">
      <span>Enter to send · Shift+Enter for a new line</span>
      <span>One request at a time per conversation</span>
    </div>
  </div>
</template>
