<script setup lang="ts">
import {
  AlertTriangle,
  Check,
  ExternalLink,
  FlaskConical,
  History,
  LoaderCircle,
  Menu,
  Moon,
  Pencil,
  Plus,
  Reply,
  Search,
  Sparkles,
  Sun,
  Trash,
  X,
} from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{
  name:
    | 'alert'
    | 'ext'
    | 'reply'
    | 'spark'
    | 'plus'
    | 'search'
    | 'pencil'
    | 'trash'
    | 'check'
    | 'close'
    | 'menu'
    | 'history'
    | 'flask'
    | 'load'
    | 'moon'
    | 'sun'
}>()

const ICONS = {
  alert: AlertTriangle,
  ext: ExternalLink,
  reply: Reply,
  spark: Sparkles,
  plus: Plus,
  search: Search,
  pencil: Pencil,
  trash: Trash,
  check: Check,
  close: X,
  menu: Menu,
  history: History,
  flask: FlaskConical,
  load: LoaderCircle,
  moon: Moon,
  sun: Sun,
} as const

const icon = computed(() => ICONS[props.name])
</script>

<template>
  <component :is="icon" class="ic" :size="16" :stroke-width="1.75" aria-hidden="true" />
</template>
