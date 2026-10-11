<script setup lang="ts">
import { onMounted } from 'vue'

import AppShell from '@/components/shell/AppShell.vue'
import ThemeSwitch from '@/components/shell/ThemeSwitch.vue'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

onMounted(() => {
  themeStore.initFromDocument()
})
</script>

<template>
  <AppShell>
    <template #sidebar>
      <div class="sb-foot">
        <ThemeSwitch />
      </div>
    </template>

    <template #default>
      <div class="placeholder">App shell (T2)</div>
    </template>

    <template #history>
      <div class="hist-placeholder">History panel (T9)</div>
    </template>
  </AppShell>
</template>

<style scoped>
.sb-foot {
  margin-top: auto;
  border-top: 1px solid var(--border);
  padding: 8px 8px 10px;
  display: grid;
  gap: 2px;
}

.placeholder,
.hist-placeholder {
  padding: 24px 20px;
  color: var(--muted);
  font-size: 13px;
}
</style>
