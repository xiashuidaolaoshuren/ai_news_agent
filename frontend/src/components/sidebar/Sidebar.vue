<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import BackendStatus from '@/components/sidebar/BackendStatus.vue'
import DeleteConfirm from '@/components/sidebar/DeleteConfirm.vue'
import SessionRow from '@/components/sidebar/SessionRow.vue'
import SessionSearchHit from '@/components/sidebar/SessionSearchHit.vue'
import ThemeSwitch from '@/components/shell/ThemeSwitch.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useSessionsStore } from '@/stores/sessions'

/** Client debounce before the search request, per the spec. */
const SEARCH_DEBOUNCE_MS = 300

const store = useSessionsStore()

const query = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(query, (next) => {
  if (searchTimer !== null) {
    clearTimeout(searchTimer)
  }
  const trimmed = next.trim()
  if (trimmed === '') {
    searchTimer = null
    void store.search('')
    return
  }
  searchTimer = setTimeout(() => {
    searchTimer = null
    void store.search(trimmed)
  }, SEARCH_DEBOUNCE_MS)
})

onUnmounted(() => {
  if (searchTimer !== null) {
    clearTimeout(searchTimer)
  }
})

const searching = computed(() => store.searchQuery !== '')

const deleteTitle = computed(() => {
  const id = store.deleteId
  return store.sessions.find((session) => session.id === id)?.title ?? ''
})
</script>

<template>
  <div class="brand">
    <div class="brand-mark" aria-hidden="true">AN</div>
    <div><b>AI News Research Agent</b><span>Local · single user</span></div>
  </div>

  <div class="sb-tools">
    <button type="button" class="btn" data-od-id="new-conversation" @click="store.createOrReuse()">
      <AppIcon name="plus" />New conversation
    </button>
    <div class="field" data-od-id="session-search">
      <AppIcon name="search" />
      <label class="sr-only" for="sess-q">Search conversations</label>
      <input
        id="sess-q"
        v-model="query"
        class="input"
        type="search"
        placeholder="Search conversations"
        autocomplete="off"
      />
    </div>
  </div>

  <div class="sb-scroll">
    <p v-if="store.deleteError" class="sb-error" role="alert">{{ store.deleteError }}</p>

    <template v-if="searching">
      <div v-if="store.searching && store.hits.length === 0" class="sb-empty">Searching…</div>
      <div v-else-if="store.hits.length === 0" class="sb-empty">
        No conversations match “{{ store.searchQuery }}”.
      </div>
      <ul v-else class="sess-list">
        <SessionSearchHit
          v-for="hit in store.hits"
          :key="hit.sessionId"
          :hit="hit"
          @open="store.openSession(hit.sessionId)"
        />
      </ul>
    </template>

    <template v-else-if="store.loading && store.sessions.length === 0">
      <div class="sb-empty">Loading conversations…</div>
    </template>

    <template v-else-if="store.sessions.length === 0">
      <div class="sb-empty">No conversations yet. Start one with New conversation.</div>
    </template>

    <template v-else>
      <template v-for="group in store.groups" :key="group.label">
        <div class="sb-group">{{ group.label }}</div>
        <ul class="sess-list">
          <template v-for="session in group.sessions" :key="session.id">
            <li class="sess-li" :data-od-id="`session-${session.id}`">
              <SessionRow
                :session="session"
                :active="session.id === store.activeId"
                :flashing="session.id === store.flashId"
                :renaming="session.id === store.renamingId"
                @open="store.openSession(session.id)"
                @request-rename="store.requestRename(session.id)"
                @submit-rename="store.rename(session.id, $event)"
                @cancel-rename="store.cancelRename()"
                @request-delete="store.requestDelete(session.id)"
              />
            </li>
            <li
              v-if="store.deleteId === session.id"
              class="sess-confirm"
              role="alertdialog"
              aria-label="Confirm delete"
              data-od-id="delete-confirm"
            >
              <DeleteConfirm
                :title="deleteTitle || 'this conversation'"
                @keep="store.cancelDelete()"
                @confirm="store.confirmDelete(session.id)"
              />
            </li>
          </template>
        </ul>
      </template>
    </template>
  </div>

  <div class="sb-foot">
    <ThemeSwitch />
    <BackendStatus />
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px 10px;
}

.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: var(--fg);
  color: var(--surface);
  display: grid;
  place-items: center;
  font: 600 12px/1 var(--font-mono);
}

.brand b {
  display: block;
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.2;
}

.brand span {
  font-size: 11.5px;
  color: var(--muted);
}

.sb-tools {
  padding: 4px 12px 10px;
  display: grid;
  gap: 8px;
}

.sb-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}

.sb-group {
  font: 500 11px/1 var(--font-mono);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 14px 8px 6px;
}

.sess-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.sess-confirm {
  margin: 2px 4px 8px;
  padding: 10px;
  border: 1px solid var(--danger-bd);
  background: var(--danger-bg);
  border-radius: 7px;
  font-size: 12.5px;
}

.sess-confirm :deep(p) {
  margin: 0 0 8px;
  color: var(--danger-ink);
}

.sess-confirm :deep(div) {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.sb-error {
  margin: 8px 4px;
  padding: 10px;
  border: 1px solid var(--danger-bd);
  background: var(--danger-bg);
  color: var(--danger-ink);
  border-radius: 7px;
  font-size: 12.5px;
}

.sb-empty {
  padding: 16px 10px;
  font-size: 12.5px;
  color: var(--muted);
}

.sb-foot {
  border-top: 1px solid var(--border);
  padding: 8px 8px 10px;
  display: grid;
  gap: 2px;
}
</style>
