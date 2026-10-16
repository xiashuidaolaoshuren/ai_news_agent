<script setup lang="ts">
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Ban,
  Check,
  Dot,
  ExternalLink,
  FlaskConical,
  History,
  Info,
  LoaderCircle,
  Menu,
  Moon,
  Pencil,
  Plus,
  RefreshCw,
  Reply,
  Search,
  Sparkles,
  Square,
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
    | 'info'
    | 'load'
    | 'moon'
    | 'sun'
    | 'dot'
    | 'refresh'
    | 'ban'
    | 'up'
    | 'down'
    | 'stop'
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
  info: Info,
  load: LoaderCircle,
  moon: Moon,
  sun: Sun,
  dot: Dot,
  refresh: RefreshCw,
  ban: Ban,
  up: ArrowUp,
  down: ArrowDown,
  stop: Square,
} as const

const icon = computed(() => ICONS[props.name])
</script>

<template>
  <component :is="icon" class="ic" :size="16" :stroke-width="1.75" aria-hidden="true" />
</template>
