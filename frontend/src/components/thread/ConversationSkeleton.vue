<script setup lang="ts">
/** Placeholder widths, matching the prototype's loading skeleton. */
const GROUPS = [[42], [94, 82, 58], [90, 70]]
</script>

<template>
  <div class="skel" data-od-id="conversation-loading" role="status" aria-label="Loading conversation">
    <div class="bubble">
      <div class="writing">
        <div class="line" style="width: 100%"></div>
        <div class="line" style="width: 64%"></div>
      </div>
    </div>
    <div class="msg-ai">
      <div class="ai-label"><b>Agent</b></div>
      <div class="section">
        <div class="set-body">
          <div v-for="(group, index) in GROUPS" :key="index" class="writing">
            <div
              v-for="width in group"
              :key="width"
              class="line"
              :style="`width: ${width}%`"
            ></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
