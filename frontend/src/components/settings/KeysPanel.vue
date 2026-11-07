<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import type {
  CredentialId,
  CredentialRowVm,
  CredentialState,
  KeyDraftKey,
  KeysVm,
} from '@/vm/settings'

const props = defineProps<{ vm: KeysVm }>()

const emit = defineEmits<{
  updateDraft: [key: KeyDraftKey, value: string]
  saveLlm: []
  saveKey: [key: KeyDraftKey]
  test: [name: string]
  clearOverride: []
  gotoSource: [name: string]
}>()

/** Prototype status chips: dot class and copy. */
const STATUS: Record<CredentialState, { dot: string; label: string }> = {
  app: { dot: '', label: 'Saved in app' },
  env: { dot: 'env', label: 'Environment' },
  none: { dot: 'off', label: 'Not set' },
  bad: { dot: 'err', label: 'Unreadable' },
}

const EMPTY_ROW: CredentialRowVm = { status: 'none', last4: null, version: null }

interface RowSpec {
  key: KeyDraftKey
  name: CredentialId
  label: string
  placeholder: string
  password: boolean
  testable: boolean
}

const LLM_ROWS: RowSpec[] = [
  { key: 'llmKey', name: 'OPENAI_API_KEY', label: 'API key', placeholder: 'Enter a new key', password: true, testable: false },
  { key: 'llmUrl', name: 'OPENAI_BASE_URL', label: 'Base URL', placeholder: 'https://…', password: false, testable: false },
  { key: 'llmModel', name: 'OPENAI_MODEL', label: 'Model', placeholder: 'provider/model-name', password: false, testable: false },
]

const SOURCE_ROWS: RowSpec[] = [
  { key: 'github', name: 'GITHUB_TOKEN', label: 'GitHub token', placeholder: 'Enter a new token', password: true, testable: true },
  { key: 'hf', name: 'HUGGINGFACE_TOKEN', label: 'Hugging Face token', placeholder: 'Enter a new token', password: true, testable: true },
  { key: 'zhihu', name: 'ZHIHU_ACCESS_SECRET', label: 'Zhihu cookie', placeholder: 'Paste a new cookie', password: true, testable: true },
]

/** Bilibili stays editable while the source is hidden; the API has no test for it. */
const BILIBILI_ROWS: RowSpec[] = [
  { key: 'bilibiliSessdata', name: 'BILIBILI_SESSDATA', label: 'SESSDATA', placeholder: 'Paste a new cookie', password: true, testable: false },
  { key: 'bilibiliBiliJct', name: 'BILIBILI_BILI_JCT', label: 'bili_jct', placeholder: 'Paste a new cookie', password: true, testable: false },
  { key: 'bilibiliBuvid3', name: 'BILIBILI_BUVID3', label: 'buvid3', placeholder: 'Paste a new cookie', password: true, testable: false },
]

function row(name: CredentialId): CredentialRowVm {
  return props.vm.rows[name] ?? EMPTY_ROW
}

function testLabel(name: string): string {
  if (props.vm.testing === name) {
    return 'Testing…'
  }
  return 'Test connection'
}

function testNote(name: string): string {
  if (props.vm.testing === name) {
    return 'Testing…'
  }
  const result = props.vm.results[name]
  if (result === undefined) {
    return ''
  }
  return result.result === 'ok'
    ? 'Connection OK. The model replied.'
    : `Test failed: ${result.reason || 'the saved credential cannot be used.'}`
}

function onInput(key: KeyDraftKey, event: Event): void {
  emit('updateDraft', key, (event.target as HTMLInputElement).value)
}
</script>

<template>
  <div
    v-if="props.vm.readOnly"
    class="alert alert-info"
    role="status"
    data-od-id="keys-read-only"
  >
    <AppIcon name="info" />
    <p>
      <b>Keys are read-only.</b> Encryption isn’t enabled on this backend, so the app won’t
      store secrets. Set them as environment variables and restart the backend; their status
      shows below.
    </p>
  </div>
  <div
    v-if="props.vm.llmUnreadable"
    class="alert alert-danger"
    role="alert"
    data-od-id="keys-unreadable-override"
  >
    <AppIcon name="alert" />
    <p>
      <b>The saved LLM API key can’t be read.</b> It overrides
      <span class="mono">LLM_API_KEY</span> from the environment, so the agent can’t reach the
      model. Replace it, or clear the saved key to use the environment value.
    </p>
    <button
      type="button"
      class="btn btn-sm btn-cancel"
      data-od-id="clear-override"
      @click="emit('clearOverride')"
    >
      Clear saved key
    </button>
  </div>
  <p class="help">
    Fields are write-only. Enter a new value to replace what’s stored; saved values are never
    displayed.
  </p>

  <section class="section" data-od-id="keys-llm-group">
    <div class="section-head">
      <h3>LLM</h3>
      <span class="sub">Key, base URL and model save together</span>
    </div>
    <div
      v-for="item in LLM_ROWS"
      :key="item.key"
      class="key-row nobtn"
      :data-od-id="`key-row-${item.key}`"
    >
      <div class="key-name">
        <label :for="`key-${item.key}`">{{ item.label }}</label>
        <span class="chip">
          <span class="dot" :class="STATUS[row(item.name).status].dot" />
          {{ STATUS[row(item.name).status].label }}
          <span v-if="row(item.name).last4" class="key-last4">…{{ row(item.name).last4 }}</span>
        </span>
      </div>
      <input
        :id="`key-${item.key}`"
        class="input"
        :type="item.password ? 'password' : 'text'"
        autocomplete="off"
        spellcheck="false"
        :placeholder="item.placeholder"
        :disabled="props.vm.readOnly"
        :value="props.vm.draft[item.key]"
        @input="onInput(item.key, $event)"
      />
      <p v-if="item.key === 'llmKey' && props.vm.llmUnreadable" class="help">
        Overrides the environment value.
      </p>
      <p v-if="props.vm.messages[item.key]" class="help" role="status">
        {{ props.vm.messages[item.key] }}
      </p>
    </div>
    <div class="key-actions">
      <button
        type="button"
        class="btn btn-primary"
        data-od-id="save-llm"
        :disabled="props.vm.readOnly"
        @click="emit('saveLlm')"
      >
        Save LLM settings
      </button>
      <button
        type="button"
        class="btn"
        data-od-id="test-llm"
        :disabled="props.vm.readOnly || props.vm.testing === 'OPENAI_API_KEY'"
        @click="emit('test', 'OPENAI_API_KEY')"
      >
        <AppIcon v-if="props.vm.testing === 'OPENAI_API_KEY'" name="load" class="spin" />
        {{ testLabel('OPENAI_API_KEY') }}
      </button>
      <p class="help" role="status">
        {{ [props.vm.messages.llm, testNote('OPENAI_API_KEY')].filter(Boolean).join(' ') }}
        Sends one short request to the model. The check may incur a small charge.
      </p>
    </div>
  </section>

  <section class="section" data-od-id="keys-source-group">
    <div class="section-head">
      <h3>Source keys</h3>
      <span class="sub">Each saves on its own</span>
    </div>
    <div
      v-for="item in SOURCE_ROWS"
      :key="item.key"
      class="key-row"
      :data-od-id="`key-row-${item.key}`"
    >
      <div class="key-name">
        <label :for="`key-${item.key}`">{{ item.label }}</label>
        <span class="chip">
          <span class="dot" :class="STATUS[row(item.name).status].dot" />
          {{ STATUS[row(item.name).status].label }}
          <span v-if="row(item.name).last4" class="key-last4">…{{ row(item.name).last4 }}</span>
        </span>
      </div>
      <input
        :id="`key-${item.key}`"
        class="input"
        type="password"
        autocomplete="off"
        spellcheck="false"
        :placeholder="item.placeholder"
        :disabled="props.vm.readOnly"
        :value="props.vm.draft[item.key]"
        @input="onInput(item.key, $event)"
      />
      <div class="key-acts">
        <button
          type="button"
          class="btn btn-sm"
          :data-od-id="`save-key-${item.key}`"
          :disabled="props.vm.readOnly"
          @click="emit('saveKey', item.key)"
        >
          Save
        </button>
        <button
          type="button"
          class="btn btn-sm"
          :data-od-id="`test-${item.name}`"
          :disabled="props.vm.readOnly || props.vm.testing === item.name"
          @click="emit('test', item.name)"
        >
          {{ testLabel(item.name) }}
        </button>
      </div>
      <button
        v-if="item.key === 'github' && props.vm.githubAuthError"
        type="button"
        class="link-btn key-warn"
        data-od-id="github-auth-link"
        @click="emit('gotoSource', 'github')"
      >
        <AppIcon name="alert" />Last check: authentication error
      </button>
      <p v-if="testNote(item.name)" class="help" role="status">{{ testNote(item.name) }}</p>
      <p v-if="props.vm.messages[item.key]" class="help" role="status">
        {{ props.vm.messages[item.key] }}
      </p>
    </div>
  </section>

  <section class="section" data-od-id="keys-bilibili-group">
    <div class="section-head">
      <h3>Bilibili</h3>
      <span class="sub">Hidden from source selection</span>
    </div>
    <div
      v-for="item in BILIBILI_ROWS"
      :key="item.key"
      class="key-row"
      :data-od-id="`key-row-${item.key}`"
    >
      <div class="key-name">
        <label :for="`key-${item.key}`">{{ item.label }}</label>
        <span class="chip">
          <span class="dot" :class="STATUS[row(item.name).status].dot" />
          {{ STATUS[row(item.name).status].label }}
          <span v-if="row(item.name).last4" class="key-last4">…{{ row(item.name).last4 }}</span>
        </span>
      </div>
      <input
        :id="`key-${item.key}`"
        class="input"
        type="password"
        autocomplete="off"
        spellcheck="false"
        :placeholder="item.placeholder"
        :disabled="props.vm.readOnly"
        :value="props.vm.draft[item.key]"
        @input="onInput(item.key, $event)"
      />
      <button
        type="button"
        class="btn btn-sm"
        :data-od-id="`save-key-${item.key}`"
        :disabled="props.vm.readOnly"
        @click="emit('saveKey', item.key)"
      >
        Save
      </button>
      <p v-if="props.vm.messages[item.key]" class="help" role="status">
        {{ props.vm.messages[item.key] }}
      </p>
    </div>
  </section>
</template>
