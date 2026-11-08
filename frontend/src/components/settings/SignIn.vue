<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'

const props = defineProps<{ error: string | null; busy: boolean }>()

const emit = defineEmits<{ submit: [token: string] }>()

const token = defineModel<string>('token', { default: '' })

function onSubmit(): void {
  if (!props.busy) {
    emit('submit', token.value)
  }
}
</script>

<template>
  <div class="signin-wrap" data-od-id="sign-in-screen">
    <form class="signin" id="signin-form" novalidate @submit.prevent="onSubmit">
      <div class="brand" style="padding: 0">
        <div class="brand-mark" aria-hidden="true">AN</div>
        <div><b>AI News Research Agent</b><span>Owner access</span></div>
      </div>
      <div>
        <h2>Sign in</h2>
        <p class="muted">Enter the owner access token configured on the backend.</p>
      </div>
      <label class="set-field">
        Owner access token
        <input
          v-model="token"
          class="input"
          id="owner-token"
          type="password"
          autocomplete="off"
          spellcheck="false"
          :aria-invalid="props.error !== null"
          :aria-describedby="props.error === null ? 'token-note' : 'token-note token-err'"
          data-od-id="owner-token-input"
        />
      </label>
      <p v-if="props.error !== null" class="err-msg" id="token-err" role="alert">
        <AppIcon name="alert" />{{ props.error }}
      </p>
      <button
        type="submit"
        class="btn btn-primary"
        :disabled="props.busy"
        data-od-id="sign-in-button"
      >
        Sign in
      </button>
      <p class="help" id="token-note">
        <AppIcon name="lock" />
        <span>The token stays for this tab only. Close the tab and you'll need to enter it again.</span>
      </p>
    </form>
  </div>
</template>
