<script setup lang="ts">
import type { AvatarVm } from '@/vm'

const props = defineProps<{ avatar: AvatarVm }>()
</script>

<template>
  <img
    v-if="props.avatar.type === 'image'"
    class="av"
    :src="props.avatar.src"
    :alt="props.avatar.alt"
    width="20"
    height="20"
  />
  <i
    v-else-if="props.avatar.type === 'initials'"
    class="mono-av"
    aria-hidden="true"
    :title="props.avatar.title"
    >{{ props.avatar.text }}</i
  >
  <span v-else-if="props.avatar.type === 'neutral'" class="av av-neutral" aria-hidden="true" />
</template>
