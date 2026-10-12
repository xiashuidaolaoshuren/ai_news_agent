<script setup lang="ts">
import bilibiliLogo from '@/assets/sources/bilibili.ico'
import githubLogo from '@/assets/sources/github.svg'
import huggingFaceLogo from '@/assets/sources/huggingface.svg'
import juyaLogo from '@/assets/sources/juya.png'
import zhihuLogo from '@/assets/sources/zhihu.ico'
import type { EntryKind } from '@/vm'

const props = defineProps<{ kind: EntryKind }>()

const LOGOS: Record<EntryKind, string> = {
  juya: juyaLogo,
  huggingface: huggingFaceLogo,
  github: githubLogo,
  zhihu: zhihuLogo,
  bilibili: bilibiliLogo,
}
</script>

<template>
  <img
    class="logo"
    :class="{ gh: props.kind === 'github' }"
    :src="LOGOS[props.kind]"
    alt=""
    width="14"
    height="14"
  />
</template>
