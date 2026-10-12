<script setup lang="ts">
const props = defineProps<{ title: string }>()

const emit = defineEmits<{ keep: []; confirm: [] }>()
</script>

<template>
  <p>Delete “{{ props.title }}”? This can’t be undone.</p>
  <div>
    <button type="button" class="btn btn-sm" @click="emit('keep')">Keep</button>
    <button type="button" class="btn btn-sm btn-danger" @click="emit('confirm')">Delete</button>
  </div>
</template>
