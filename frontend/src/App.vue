<script setup lang="ts">
import { computed, onMounted, onUnmounted, useTemplateRef, watch } from 'vue'

import Sidebar from '@/components/sidebar/Sidebar.vue'
import AppShell from '@/components/shell/AppShell.vue'
import ChatHead from '@/components/shell/ChatHead.vue'
import Thread from '@/components/thread/Thread.vue'
import { useSessionsStore } from '@/stores/sessions'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const sessions = useSessionsStore()

const shell = useTemplateRef<InstanceType<typeof AppShell>>('shell')

/** An open inline edit in the sidebar takes Escape before the shell closes overlays. */
const inlineEditOpen = computed(
  () => sessions.renamingId !== null || sessions.deleteId !== null,
)

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !inlineEditOpen.value) {
    return
  }
  if (sessions.renamingId !== null) {
    sessions.cancelRename()
    return
  }
  sessions.cancelDelete()
}

// The prototype dismisses the sidebar overlay as soon as a conversation is chosen.
watch(
  () => sessions.activeId,
  () => {
    shell.value?.closeSidebar()
  },
)

onMounted(() => {
  themeStore.initFromDocument()
  document.addEventListener('keydown', onKeydown)
  void sessions.loadSessions()
  void sessions.loadHealth()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <AppShell ref="shell" :escape-guard="inlineEditOpen">
    <template #sidebar>
      <Sidebar />
    </template>

    <template #header>
      <ChatHead
        :hist-open="shell?.histOpen ?? false"
        @open-sidebar="shell?.openSidebar()"
        @toggle-history="shell?.toggleHistory()"
      />
    </template>

    <template #default>
      <Thread :messages="[]" />
    </template>

    <template #history>
      <div class="hist-placeholder">History panel (T9)</div>
    </template>
  </AppShell>
</template>

<style scoped>
.hist-placeholder {
  padding: 24px 20px;
  color: var(--muted);
  font-size: 13px;
}
</style>
