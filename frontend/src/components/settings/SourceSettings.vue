<script setup lang="ts">
import type { OutputLanguage } from '@/stores/settings'
import type { SourceProfileVm } from '@/vm/settings'

const props = defineProps<{
  language: OutputLanguage
  profiles: SourceProfileVm[]
  fieldErrors: Record<string, string>
}>()

const emit = defineEmits<{
  updateLanguage: [language: OutputLanguage]
  updateProfile: [profile: SourceProfileVm]
}>()

const LABELS: Record<SourceProfileVm['name'], string> = {
  juya: 'Juya',
  github: 'GitHub',
  huggingface: 'Hugging Face',
  openrouter: 'OpenRouter',
  zhihu: 'Zhihu',
  bilibili: 'Bilibili',
}

function replace(profile: SourceProfileVm, patch: Record<string, unknown>): void {
  emit('updateProfile', { ...profile, ...patch } as SourceProfileVm)
}
</script>

<template>
  <section class="section" data-od-id="settings-output-language">
    <label class="set-field">
      Output language
      <select
        class="input"
        :value="props.language"
        @change="emit('updateLanguage', ($event.target as HTMLSelectElement).value as OutputLanguage)"
      >
        <option value="source_default">Source default</option>
        <option value="en">English</option>
        <option value="zh-CN">Simplified Chinese</option>
      </select>
    </label>
  </section>
  <section
    v-for="profile in props.profiles"
    :id="`set-${profile.name}`"
    :key="profile.name"
    class="section"
    :data-od-id="`settings-source-${profile.name}`"
  >
    <div class="section-head">
      <h3>{{ LABELS[profile.name] }}</h3>
      <span v-if="profile.hidden" class="sub">Hidden from source selection</span>
    </div>
    <div class="set-body">
      <template v-if="profile.name === 'juya'">
        <label class="set-field">
          Item count
          <input
            class="input"
            type="number"
            min="1"
            max="50"
            :disabled="profile.itemCount === 'all'"
            :value="profile.itemCount === 'all' ? '' : profile.itemCount"
            @change="replace(profile, { itemCount: Number(($event.target as HTMLInputElement).value) })"
          />
        </label>
        <button
          type="button"
          data-od-id="juya-count-all"
          :aria-pressed="profile.itemCount === 'all'"
          @click="replace(profile, { itemCount: profile.itemCount === 'all' ? 5 : 'all' })"
        >
          All
        </button>
      </template>
      <label v-else-if="'itemCount' in profile" class="set-field">
        Item count
        <input
          class="input"
          type="number"
          min="1"
          max="50"
          :value="profile.itemCount"
          @change="replace(profile, { itemCount: Number(($event.target as HTMLInputElement).value) })"
        />
      </label>
      <label v-if="profile.name === 'openrouter'" class="set-field">
        Free token pricing only
        <input
          type="checkbox"
          data-od-id="openrouter-free-only"
          :checked="profile.freeOnly"
          @change="replace(profile, { freeOnly: ($event.target as HTMLInputElement).checked })"
        />
      </label>
      <p v-if="props.fieldErrors[profile.name]" class="err-msg">{{ props.fieldErrors[profile.name] }}</p>
    </div>
  </section>
</template>
