<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import EntryRow from '@/components/thread/EntryRow.vue'
import MarkdownReply from '@/components/thread/MarkdownReply.vue'
import SourceTag from '@/components/thread/SourceTag.vue'
import type { HistoryFilters, HistoryMatchVm, HistoryPanelVm } from '@/vm'

const props = defineProps<{ vm: HistoryPanelVm }>()

const emit = defineEmits<{
  updateFilter: [patch: Partial<HistoryFilters>]
  open: [match: HistoryMatchVm]
  clear: []
  retry: []
  closeResult: []
  ask: [title: string]
  close: []
}>()

/**
 * Opening is read-only. The prototype named the live digest that stayed
 * unchanged; the host app has no dependency on the thread here, so the note is
 * the spec's rule on its own.
 */
const OPENED_NOTE = 'Opened from history. The current conversation is unchanged.'

/** The result actions are the prototype's row of buttons under the saved entry. */
function text(event: Event): string {
  return (event.target as HTMLInputElement | HTMLSelectElement).value
}
</script>

<template>
  <div class="hist-head">
    <AppIcon name="history" />
    <h2>History</h2>
    <span class="muted" style="font-size: 12px">all past digests</span>
    <span class="grow" />
    <button
      type="button"
      class="icon-btn"
      aria-label="Close history"
      data-od-id="history-close"
      @click="emit('close')"
    >
      <AppIcon name="close" />
    </button>
  </div>

  <form
    class="hist-filters"
    data-od-id="history-filters"
    @submit.prevent
  >
    <div class="field">
      <AppIcon name="search" />
      <label class="sr-only" for="history-text">Search text</label>
      <input
        id="history-text"
        class="input"
        type="search"
        placeholder="Search titles and summaries"
        autocomplete="off"
        data-od-id="history-text"
        :value="props.vm.filters.text"
        @input="emit('updateFilter', { text: text($event) })"
      />
    </div>
    <div class="hist-row">
      <label>
        Source
        <select
          class="input"
          data-od-id="history-source"
          :value="props.vm.filters.source"
          @change="emit('updateFilter', { source: text($event) })"
        >
          <option
            v-for="option in props.vm.sourceOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </label>
      <label>
        Topic
        <input
          class="input"
          placeholder="All topics"
          autocomplete="off"
          data-od-id="history-topic"
          :value="props.vm.filters.topic"
          @input="emit('updateFilter', { topic: text($event) })"
        />
      </label>
    </div>
    <div class="hist-row">
      <label>
        From
        <input
          class="input"
          type="date"
          data-od-id="history-date-from"
          :value="props.vm.filters.from"
          @input="emit('updateFilter', { from: text($event) })"
        />
      </label>
      <label>
        To
        <input
          class="input"
          type="date"
          data-od-id="history-date-to"
          :value="props.vm.filters.to"
          @input="emit('updateFilter', { to: text($event) })"
        />
      </label>
    </div>
  </form>

  <div class="hist-bar">
    <span class="hist-count" aria-live="polite">
      <AppIcon v-if="props.vm.state === 'loading'" name="load" class="spin" />
      <span>{{ props.vm.countLabel }}</span>
    </span>
    <button type="button" class="btn btn-ghost btn-sm" @click="emit('clear')">
      Clear filters
    </button>
  </div>

  <div v-if="props.vm.notes.length > 0" class="hist-notes">
    <p v-for="note in props.vm.notes" :key="note">{{ note }}</p>
  </div>

  <div class="hist-scroll">
    <div
      v-if="props.vm.opened"
      class="opened fade-in"
      data-od-id="history-opened-result"
    >
      <div class="opened-head">
        <AppIcon name="info" />
        <span>{{ OPENED_NOTE }}</span>
        <span class="grow" />
        <button
          type="button"
          class="icon-btn"
          aria-label="Close result"
          @click="emit('closeResult')"
        >
          <AppIcon name="close" />
        </button>
      </div>
      <div class="opened-body">
        <div class="hit-meta">
          <span class="ref">{{ props.vm.opened.match.token }}</span>
          <span class="mono">{{ props.vm.opened.match.dateLabel }}</span>
          <SourceTag :kind="props.vm.opened.match.sourceKind" />
          <span v-if="props.vm.opened.match.topics.length > 0">{{
            props.vm.opened.match.topics.join(' · ')
          }}</span>
        </div>
        <h3 v-if="props.vm.opened.item?.entry == null">
          {{ props.vm.opened.match.title }}
        </h3>
        <p v-if="props.vm.opened.loading" class="muted">Loading the saved entry…</p>
        <p v-else-if="props.vm.opened.error" class="hist-error">
          {{ props.vm.opened.error }}
        </p>
        <ul v-else-if="props.vm.opened.item?.entry" class="entries">
          <EntryRow :entry="props.vm.opened.item.entry" @followup="emit('ask', $event)" />
        </ul>
        <MarkdownReply
          v-else-if="props.vm.opened.item"
          :text="props.vm.opened.item.markdown"
        />
        <div class="opened-actions">
          <a
            v-if="props.vm.opened.match.url"
            class="btn btn-sm"
            :href="props.vm.opened.match.url"
            target="_blank"
            rel="noopener"
            ><AppIcon name="ext" />Open source page</a
          >
          <button
            type="button"
            class="btn btn-sm btn-ghost"
            @click="emit('ask', props.vm.opened.match.title)"
          >
            <AppIcon name="reply" />Ask in chat
          </button>
        </div>
      </div>
    </div>

    <ul class="hist-list">
      <li
        v-for="match in props.vm.matches"
        :key="match.token"
        class="hit"
        :class="{ open: props.vm.opened?.match.token === match.token }"
        :data-od-id="`history-result-d${match.digestId}-r${match.rank}`"
      >
        <div class="hit-meta">
          <span class="ref">{{ match.token }}</span>
          <span class="mono">{{ match.dateLabel }}</span>
          <SourceTag :kind="match.sourceKind" />
        </div>
        <button type="button" class="hit-title" @click="emit('open', match)">
          {{ match.title }}
        </button>
        <a
          v-if="match.url && match.host"
          class="ext"
          :href="match.url"
          target="_blank"
          rel="noopener"
          >{{ match.host }}<AppIcon name="ext" /></a
        >
        <p v-if="match.excerpt" class="hit-excerpt">{{ match.excerpt }}</p>
      </li>

      <li
        v-if="props.vm.state === 'idle'"
        class="hist-empty"
        data-od-id="history-idle"
      >
        <b>{{ props.vm.emptyTitle }}</b>
        <p>{{ props.vm.emptyBody }}</p>
      </li>
      <li
        v-else-if="props.vm.state === 'empty'"
        class="hist-empty"
        data-od-id="history-no-matches"
      >
        <b>{{ props.vm.emptyTitle }}</b>
        <p>{{ props.vm.emptyBody }}</p>
        <button type="button" class="btn btn-sm" @click="emit('clear')">Clear filters</button>
      </li>
      <li
        v-else-if="props.vm.state === 'error'"
        class="hist-empty"
        data-od-id="history-error"
      >
        <b class="hist-error">Search failed</b>
        <p>{{ props.vm.error }}</p>
        <button type="button" class="btn btn-sm" @click="emit('retry')">Retry</button>
      </li>
    </ul>
  </div>
</template>
