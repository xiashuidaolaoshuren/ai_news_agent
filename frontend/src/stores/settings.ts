import { defineStore } from 'pinia'
import { reactive } from 'vue'

import {
  getOutputLanguageApiV1SettingsLanguageGet,
  listSourceProfilesApiV1SettingsSourcesGet,
  saveOutputLanguageApiV1SettingsLanguagePut,
  saveSourceProfileApiV1SettingsSourcesNamePut,
} from '@/api/generated/sdk.gen'
import { setupApiClient } from '@/api/setupClient'
import {
  toSourceProfilesVm,
  type SourceProfileVm,
} from '@/vm/settings'

const COUNTS_SEEN_KEY = 'anra-counts-seen'

export type OutputLanguage = 'source_default' | 'en' | 'zh-CN'

export interface SettingsDraft {
  language: OutputLanguage
  profiles: SourceProfileVm[]
}

/** Server calls the settings panel needs, injected for tests. */
export interface SettingsDeps {
  listProfiles(): Promise<unknown>
  getLanguage(): Promise<string>
  saveProfile(name: string, body: Record<string, unknown>): Promise<void>
  saveLanguage(language: string): Promise<void>
  readCountsSeen(): boolean
  writeCountsSeen(): void
}

function asLanguage(value: string): OutputLanguage {
  if (value === 'en' || value === 'zh-CN' || value === 'source_default') {
    return value
  }
  return 'source_default'
}

function cloneDraft(draft: SettingsDraft): SettingsDraft {
  return JSON.parse(JSON.stringify(draft)) as SettingsDraft
}

function profileBody(profile: SourceProfileVm): Record<string, unknown> {
  switch (profile.name) {
    case 'juya':
      return { item_count: profile.itemCount }
    case 'github':
      return {
        item_count: profile.itemCount,
        keywords: profile.keywords,
        min_stars: profile.minStars,
        language: profile.language,
      }
    case 'huggingface':
      return { item_count: profile.itemCount, pipeline_tag: profile.pipelineTag }
    case 'openrouter':
      return { item_count: profile.itemCount, free_only: profile.freeOnly }
    case 'zhihu':
      return { item_count: profile.itemCount }
    case 'bilibili':
      return {}
  }
}

/** Settings dialog state. The draft is what the form edits. */
export function createSettingsController(deps: SettingsDeps) {
  const state = reactive({
    language: 'source_default' as OutputLanguage,
    draft: { language: 'source_default', profiles: [] } as SettingsDraft,
    fieldErrors: {} as Record<string, string>,
    saved: false,
    loadError: null as string | null,
    isOpen: false,
    tab: 'sources' as 'sources' | 'keys',
    focus: null as string | null,
    countsSeen: deps.readCountsSeen(),
  })
  let saved: SettingsDraft = cloneDraft(state.draft)

  async function load(): Promise<void> {
    state.loadError = null
    try {
      const profiles = toSourceProfilesVm(await deps.listProfiles())
      const language = asLanguage(await deps.getLanguage())
      state.language = language
      state.draft = { language, profiles }
      saved = cloneDraft(state.draft)
    } catch (error) {
      state.loadError = error instanceof Error ? error.message : 'Could not load settings.'
    }
  }

  async function save(): Promise<void> {
    state.fieldErrors = {}
    state.saved = false
    let rejected = false
    for (const profile of state.draft.profiles) {
      const before = saved.profiles.find((item) => item.name === profile.name)
      if (JSON.stringify(before) === JSON.stringify(profile)) {
        continue
      }
      try {
        await deps.saveProfile(profile.name, profileBody(profile))
      } catch (error) {
        state.fieldErrors[profile.name] =
          error instanceof Error ? error.message : 'Could not save this source.'
        rejected = true
      }
    }
    if (state.draft.language !== saved.language) {
      await deps.saveLanguage(state.draft.language)
    }
    if (rejected) {
      return
    }
    saved = cloneDraft(state.draft)
    state.language = state.draft.language
    state.saved = true
  }

  function dismissCounts(): void {
    deps.writeCountsSeen()
    state.countsSeen = true
  }

  function open(tab: 'sources' | 'keys' = 'sources', focus: string | null = null): void {
    state.tab = tab
    state.focus = focus
    state.isOpen = true
    dismissCounts()
    void load()
  }

  function close(): void {
    state.isOpen = false
    state.focus = null
  }

  function updateProfile(profile: SourceProfileVm): void {
    state.draft.profiles = state.draft.profiles.map((item) =>
      item.name === profile.name ? profile : item,
    )
  }

  return Object.assign(state, {
    load,
    save,
    open,
    close,
    dismissCounts,
    updateProfile,
  })
}

/** Production dependencies wired to the generated settings client. */
export function defaultSettingsDeps(): SettingsDeps {
  setupApiClient()
  return {
    async listProfiles(): Promise<unknown> {
      const result = await listSourceProfilesApiV1SettingsSourcesGet()
      if (result.data === undefined) {
        throw new Error('Could not load source settings.')
      }
      return result.data
    },
    async getLanguage(): Promise<string> {
      const result = await getOutputLanguageApiV1SettingsLanguageGet()
      return result.data?.language ?? 'source_default'
    },
    async saveProfile(name, body): Promise<void> {
      try {
        await saveSourceProfileApiV1SettingsSourcesNamePut({
          path: { name },
          body,
          throwOnError: true,
        })
      } catch (caught) {
        const detail = (caught as { detail?: unknown }).detail
        throw new Error(
          typeof detail === 'string'
            ? detail
            : caught instanceof Error
              ? caught.message
              : 'Could not save this source.',
        )
      }
    },
    async saveLanguage(language): Promise<void> {
      await saveOutputLanguageApiV1SettingsLanguagePut({
        body: { language: language as OutputLanguage },
      })
    },
    readCountsSeen: () => {
      try {
        return localStorage.getItem(COUNTS_SEEN_KEY) === '1'
      } catch {
        return false
      }
    },
    writeCountsSeen: () => {
      try {
        localStorage.setItem(COUNTS_SEEN_KEY, '1')
      } catch {
        // A private window that blocks storage still hides the notice for this page.
      }
    },
  }
}

export const useSettingsStore = defineStore('settings', () =>
  createSettingsController(defaultSettingsDeps()),
)
