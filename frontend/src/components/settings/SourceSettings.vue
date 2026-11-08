<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import SourceLogo from '@/components/thread/SourceLogo.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import type { OutputLanguage } from '@/stores/settings'
import type { SourceProfileVm } from '@/vm/settings'

type SourceName = SourceProfileVm['name']

const props = defineProps<{
  language: OutputLanguage
  profiles: SourceProfileVm[]
  fieldErrors: Record<string, string>
  /** The newest GitHub credential check failed, as `GET /sources` reports it. */
  githubAuthError?: boolean
}>()

const emit = defineEmits<{
  updateLanguage: [language: OutputLanguage]
  updateProfile: [profile: SourceProfileVm]
  /** "Open Keys" on the GitHub auth warning. */
  gotoKeys: []
}>()

const LABELS: Record<SourceName, string> = {
  juya: 'Juya',
  huggingface: 'Hugging Face',
  openrouter: 'OpenRouter',
  github: 'GitHub',
  zhihu: 'Zhihu',
  bilibili: 'Bilibili',
}

/** Section subtitles and the prototype's own order. */
const SUBS: Record<SourceName, string> = {
  juya: '橘鸦 AI 早报',
  huggingface: 'Trending models',
  openrouter: 'New models',
  github: 'Trending repositories',
  zhihu: 'Discussions',
  bilibili: '',
}

const ORDER: SourceName[] = ['juya', 'huggingface', 'openrouter', 'github', 'zhihu', 'bilibili']

const PIPELINES = [
  'any',
  'text-generation',
  'image-text-to-text',
  'automatic-speech-recognition',
  'text-to-image',
  'text-to-video',
]

const LANGUAGES = ['any', 'Python', 'TypeScript', 'JavaScript', 'Rust', 'Go']

const ordered = computed(() =>
  [...props.profiles].sort((a, b) => ORDER.indexOf(a.name) - ORDER.indexOf(b.name)),
)

/** Only the sources the app has artwork for get a head tile. */
const LOGO_KINDS: Partial<Record<SourceName, 'juya' | 'huggingface' | 'github' | 'zhihu' | 'bilibili'>> = {
  juya: 'juya',
  huggingface: 'huggingface',
  github: 'github',
  zhihu: 'zhihu',
  bilibili: 'bilibili',
}

/** Keyword text stays local while typing; the parsed list goes to the profile. */
const keywordText = reactive<Record<string, string>>({})

function keywordsFor(profile: SourceProfileVm & { keywords: string[] }): string {
  return keywordText[profile.name] ?? profile.keywords.join(', ')
}

function onKeywords(profile: SourceProfileVm & { keywords: string[] }, event: Event): void {
  const text = (event.target as HTMLInputElement).value
  keywordText[profile.name] = text
  const keywords = text
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item !== '')
  replace(profile, { keywords })
}

function replace(profile: SourceProfileVm, patch: Record<string, unknown>): void {
  emit('updateProfile', { ...profile, ...patch } as SourceProfileVm)
}

/** A count the user cleared or mistyped stays invalid, so Save can name it. */
function countOf(event: Event): number {
  return Number((event.target as HTMLInputElement).value)
}

/** Minimum stars is not range-checked; a blank or unreadable value falls back to 0. */
function starsOr(value: number): number {
  return Number.isFinite(value) ? value : 0
}

/**
 * The prototype keeps Juya's count and its All flag apart, so the number stays
 * visible and editable-again while All is on. The API stores only `all`, so the
 * last number seen here stands in, starting from the prototype's default of 5.
 */
const juyaCount = ref(5)

watch(
  () => props.profiles.find((profile) => profile.name === 'juya'),
  (profile) => {
    if (profile?.name === 'juya' && typeof profile.itemCount === 'number') {
      juyaCount.value = profile.itemCount
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="section" data-od-id="settings-output-language">
    <div class="set-body">
      <label class="set-field">
        Output language
        <select
          class="input"
          data-od-id="settings-output-language-select"
          :value="props.language"
          @change="emit('updateLanguage', ($event.target as HTMLSelectElement).value as OutputLanguage)"
        >
          <option value="source_default">Source default</option>
          <option value="en">English</option>
          <option value="zh-CN">Simplified Chinese</option>
        </select>
      </label>
      <p class="help">
        Source default keeps each story in the language it was published in. Applies to every
        source.
      </p>
    </div>
  </section>
  <section
    v-for="profile in ordered"
    :id="`set-${profile.name}`"
    :key="profile.name"
    class="section"
    :data-od-id="`settings-source-${profile.name}`"
  >
    <div class="section-head">
      <span v-if="LOGO_KINDS[profile.name]" class="tile">
        <SourceLogo :kind="LOGO_KINDS[profile.name]!" />
      </span>
      <h3>{{ LABELS[profile.name] }}</h3>
      <span v-if="SUBS[profile.name]" class="sub">{{ SUBS[profile.name] }}</span>
      <span class="grow" />
      <span v-if="profile.hidden" class="chip">
        <AppIcon name="ban" />Hidden from source selection
      </span>
      <span v-if="profile.name === 'github' && props.githubAuthError" class="chip">
        <span class="dot warn" />Auth error
      </span>
    </div>
    <div class="set-body">
      <div v-if="profile.name === 'github' && props.githubAuthError" class="alert alert-danger" role="alert" id="gh-auth" tabindex="-1" data-od-id="github-auth-warning">
        <AppIcon name="alert" />
        <p>
          <b>Last check: authentication error.</b> GitHub rejected the token (401). GitHub
          requests fail until the token is replaced.
        </p>
        <button type="button" class="btn btn-sm btn-cancel act" @click="emit('gotoKeys')">
          Open Keys
        </button>
      </div>
      <template v-if="profile.name === 'juya'">
        <div class="set-grid">
          <div class="set-field">
            <label for="cnt-juya">Item count</label>
            <div class="count-row">
              <input
                id="cnt-juya"
                class="input"
                type="number"
                min="1"
                max="50"
                inputmode="numeric"
                :disabled="profile.itemCount === 'all'"
                :value="profile.itemCount === 'all' ? juyaCount : profile.itemCount"
                :aria-invalid="props.fieldErrors.juya !== undefined"
                aria-describedby="juya-n-help"
                data-od-id="juya-count-5"
                @change="
                  juyaCount = countOf($event);
                  replace(profile, { itemCount: countOf($event) })
                "
              />
              <button
                type="button"
                class="btn btn-sm"
                data-od-id="juya-count-all"
                :aria-pressed="profile.itemCount === 'all'"
                @click="replace(profile, { itemCount: profile.itemCount === 'all' ? 5 : 'all' })"
              >
                All
              </button>
            </div>
          </div>
        </div>
        <p class="help" id="juya-n-help">1 to 50 stories, or All for every story in the issue.</p>
        <div
          v-if="profile.itemCount === 'all'"
          class="alert alert-warn"
          role="status"
          data-od-id="juya-all-warning"
        >
          <AppIcon name="alert" />
          <p>
            <b>All can return more than 20 stories.</b> When a request would include more than
            20, you’ll be asked to confirm before the digest is written.
          </p>
        </div>
      </template>
      <template v-else-if="profile.name === 'bilibili'">
        <p class="help">
          Not offered in the composer or the history source filter, so it has no item count.
          Its cookies stay editable on the Keys tab.
        </p>
      </template>
      <template v-else>
        <div class="set-grid">
          <label class="set-field">
            Item count
            <input
              class="input"
              type="number"
              min="1"
              max="50"
              inputmode="numeric"
              :data-od-id="`count-${profile.name}`"
              :value="'itemCount' in profile ? profile.itemCount : ''"
              :aria-invalid="props.fieldErrors[profile.name] !== undefined"
              @change="replace(profile, { itemCount: countOf($event) })"
            />
          </label>
          <template v-if="profile.name === 'github'">
            <label class="set-field">
              Minimum stars
              <input
                class="input"
                type="number"
                min="0"
                step="50"
                inputmode="numeric"
                data-od-id="github-min-stars"
                :value="profile.minStars"
                @change="replace(profile, { minStars: starsOr(Number(($event.target as HTMLInputElement).value)) })"
              />
            </label>
            <label class="set-field">
              Language
              <select
                class="input"
                data-od-id="github-language"
                :value="profile.language ?? 'any'"
                @change="replace(profile, { language: ($event.target as HTMLSelectElement).value === 'any' ? null : ($event.target as HTMLSelectElement).value })"
              >
                <option v-for="item in LANGUAGES" :key="item" :value="item">
                  {{ item === 'any' ? 'Any language' : item }}
                </option>
              </select>
            </label>
          </template>
          <label v-else-if="profile.name === 'huggingface'" class="set-field">
            Pipeline
            <select
              class="input"
              data-od-id="hf-pipeline"
              :value="profile.pipelineTag ?? 'any'"
              @change="replace(profile, { pipelineTag: ($event.target as HTMLSelectElement).value === 'any' ? null : ($event.target as HTMLSelectElement).value })"
            >
              <option v-for="item in PIPELINES" :key="item" :value="item">
                {{ item === 'any' ? 'Any pipeline' : item }}
              </option>
            </select>
          </label>
        </div>
        <label v-if="profile.name === 'github'" class="set-field">
          Keywords
          <input
            class="input"
            data-od-id="github-keywords"
            :value="keywordsFor(profile)"
            placeholder="Comma-separated, e.g. agent, mcp"
            @input="onKeywords(profile, $event)"
          />
        </label>
        <p v-if="profile.name === 'openrouter' && props.fieldErrors.openrouter" class="err-msg">
          <AppIcon name="alert" />{{ props.fieldErrors.openrouter }}
        </p>
        <button
          v-if="profile.name === 'openrouter'"
          type="button"
          class="theme-sw tall"
          role="switch"
          :aria-checked="profile.freeOnly"
          data-od-id="openrouter-free-only"
          @click="replace(profile, { freeOnly: !profile.freeOnly })"
        >
          <span class="lbl">
            Free token pricing only
            <span class="help">Only include models listed at $0 for input and output tokens.</span>
          </span>
          <span class="track" aria-hidden="true" />
        </button>
      </template>
      <p v-if="profile.name !== 'openrouter' && props.fieldErrors[profile.name]" class="err-msg">
        <AppIcon name="alert" />{{ props.fieldErrors[profile.name] }}
      </p>
    </div>
  </section>
</template>
