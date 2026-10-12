<script setup lang="ts">
import AppIcon from '@/components/thread/AppIcon.vue'
import { hostOf } from '@/vm'
import type { JuyaIssueVm } from '@/vm'

const props = defineProps<{ issue: JuyaIssueVm }>()
</script>

<template>
  <div class="issue" data-od-id="juya-issue-cover">
    <img
      v-if="props.issue.coverUrl"
      :src="props.issue.coverUrl"
      :alt="props.issue.coverAlt ?? props.issue.eyebrow"
      width="1080"
      height="460"
      loading="lazy"
    />
    <div class="issue-meta">
      <span class="eyebrow">{{ props.issue.eyebrow }}</span>
      <b v-if="props.issue.leadTitle">{{ props.issue.leadTitle }}</b>
      <a
        v-if="props.issue.issueUrl"
        class="ext"
        :href="props.issue.issueUrl"
        target="_blank"
        rel="noopener"
        >{{ hostOf(props.issue.issueUrl) }}<AppIcon name="ext" /></a
      >
    </div>
  </div>
</template>
