import { defineStore } from 'pinia'
import { reactive, toRefs } from 'vue'

import {
  deleteCredentialApiV1SettingsCredentialsNameDelete,
  deleteLlmCredentialsApiV1SettingsCredentialsLlmDelete,
  getOutputLanguageApiV1SettingsLanguageGet,
  listCredentialsApiV1SettingsCredentialsGet,
  listSourceProfilesApiV1SettingsSourcesGet,
  saveCredentialApiV1SettingsCredentialsNamePut,
  saveLlmCredentialsApiV1SettingsCredentialsLlmPut,
  saveOutputLanguageApiV1SettingsLanguagePut,
  saveSourceProfileApiV1SettingsSourcesNamePut,
  testCredentialApiV1SettingsCredentialsNameTestPost,
} from '@/api/generated/sdk.gen'
import { setupApiClient } from '@/api/setupClient'
import {
  EMPTY_KEYS_DRAFT,
  toCredentialsVm,
  toSourceProfilesVm,
  type CredentialTestOutcome,
  type CredentialsVm,
  type KeysDraft,
  type SourceProfileVm,
} from '@/vm/settings'

export type OutputLanguage = 'source_default' | 'en' | 'zh-CN'

export interface SettingsDraft {
  language: OutputLanguage
  profiles: SourceProfileVm[]
}

/** What the LLM group saves in one PUT. */
export interface LlmCredentialInput {
  apiKey: string
  baseUrl: string | null
  model: string | null
}

/** Server calls the settings panel needs, injected for tests. */
export interface SettingsDeps {
  listProfiles(): Promise<unknown>
  getLanguage(): Promise<string>
  saveProfile(name: string, body: Record<string, unknown>): Promise<void>
  saveLanguage(language: string): Promise<void>
  listCredentials(): Promise<unknown>
  saveLlm(input: LlmCredentialInput): Promise<unknown>
  saveCredential(name: string, value: string): Promise<unknown>
  deleteLlm(): Promise<void>
  deleteCredential(name: string): Promise<void>
  testCredential(name: string): Promise<CredentialTestOutcome>
}

/** A settings call the API refused; `status` decides what the panel explains. */
export class SettingsRequestError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'SettingsRequestError'
    this.status = status
  }
}

/** Keys panel row to the credential name its PUT writes. */
export const CREDENTIAL_NAME_BY_KEY: Partial<Record<keyof KeysDraft, string>> = {
  github: 'GITHUB_TOKEN',
  hf: 'HUGGINGFACE_TOKEN',
  zhihu: 'ZHIHU_ACCESS_SECRET',
  bilibiliSessdata: 'BILIBILI_SESSDATA',
  bilibiliBiliJct: 'BILIBILI_BILI_JCT',
  bilibiliBuvid3: 'BILIBILI_BUVID3',
}

const EMPTY_CREDENTIALS: CredentialsVm = { readOnly: false, rows: {}, llmUnreadable: false }

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

/** Item counts are whole stories per source; the prototype's range and message. */
export const COUNT_MIN = 1
export const COUNT_MAX = 50
export const COUNT_MESSAGE = `Item count must be a whole number from ${COUNT_MIN} to ${COUNT_MAX}.`

/** Sources whose draft carries an item count. Bilibili has none. */
function hasCount(profile: SourceProfileVm): boolean {
  return 'itemCount' in profile
}

/**
 * The first source with an unusable count, or null. Juya is exempt while All is
 * on: its input keeps the stored number but the request takes the whole issue.
 */
function firstBadCount(profiles: SourceProfileVm[]): string | null {
  for (const profile of profiles) {
    if (!hasCount(profile) || profile.name === 'bilibili') {
      continue
    }
    if (profile.name === 'juya' && profile.itemCount === 'all') {
      continue
    }
    const count = profile.itemCount
    if (typeof count !== 'number' || !Number.isInteger(count) || count < COUNT_MIN || count > COUNT_MAX) {
      return profile.name
    }
  }
  return null
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
    credentials: { ...EMPTY_CREDENTIALS } as CredentialsVm,
    keysDraft: { ...EMPTY_KEYS_DRAFT } as KeysDraft,
    keysMessage: {} as Record<string, string>,
    testResults: {} as Record<string, CredentialTestOutcome>,
    testing: null as string | null,
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
    await loadCredentials()
  }

  async function loadCredentials(): Promise<void> {
    try {
      state.credentials = toCredentialsVm(await deps.listCredentials())
    } catch {
      state.credentials = { ...EMPTY_CREDENTIALS }
    }
  }

  async function save(): Promise<void> {
    state.fieldErrors = {}
    state.saved = false
    const bad = firstBadCount(state.draft.profiles)
    if (bad !== null) {
      state.fieldErrors[bad] = COUNT_MESSAGE
      // The dialog opens on that section, so the message is not off screen.
      state.focus = bad
      return
    }
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

  /**
   * Record a refused write. A 409 means the backend has no encryption key, so
   * every write switches to read-only; anything else keeps the panel usable.
   */
  function refuseWrite(key: string, error: unknown, fallback: string): void {
    if (error instanceof SettingsRequestError && error.status === 409) {
      state.credentials = { ...state.credentials, readOnly: true }
    }
    state.keysMessage[key] =
      error instanceof Error && error.message !== '' ? error.message : fallback
  }

  async function saveLlm(): Promise<void> {
    const draft = state.keysDraft
    state.keysMessage = {}
    // The API requires a key on every LLM write and never returns the stored one,
    // so the panel cannot reuse it; the user re-enters it.
    if (draft.llmKey.trim() === '') {
      state.keysMessage.llm =
        'Enter the API key to save the LLM settings. Saving never reuses the stored key.'
      return
    }
    try {
      state.credentials = toCredentialsVm(
        await deps.saveLlm({
          apiKey: draft.llmKey,
          baseUrl: draft.llmUrl.trim() === '' ? null : draft.llmUrl.trim(),
          model: draft.llmModel.trim() === '' ? null : draft.llmModel.trim(),
        }),
      )
    } catch (error) {
      refuseWrite('llm', error, 'Could not save the LLM settings.')
      return
    }
    state.keysDraft.llmKey = ''
    state.keysDraft.llmUrl = ''
    state.keysDraft.llmModel = ''
    state.keysMessage.llm = 'Saved in app.'
  }

  /** Save one source credential; saving never reads the stored value back. */
  async function saveCredential(key: keyof KeysDraft): Promise<void> {
    const name = CREDENTIAL_NAME_BY_KEY[key]
    if (name === undefined) {
      return
    }
    state.keysMessage = {}
    // An empty value would store an empty secret over a working one.
    if (state.keysDraft[key].trim() === '') {
      state.keysMessage[key] = 'Enter a value to save.'
      return
    }
    try {
      state.credentials = toCredentialsVm(await deps.saveCredential(name, state.keysDraft[key]))
    } catch (error) {
      refuseWrite(key, error, 'Could not save this credential.')
      return
    }
    state.keysDraft[key] = ''
    state.keysMessage[key] = 'Saved in app. The value won’t be shown again.'
  }

  /** Drop the saved LLM override so the environment value applies again. */
  async function clearLlmOverride(): Promise<void> {
    state.keysMessage = {}
    try {
      await deps.deleteLlm()
    } catch (error) {
      refuseWrite('llm', error, 'Could not clear the saved key.')
      return
    }
    await loadCredentials()
    state.keysMessage.llm = 'Saved key cleared. Using OPENAI_API_KEY from the environment.'
  }

  /** Test one credential. The result replaces any earlier one for that name. */
  async function testCredential(name: string): Promise<void> {
    const rest = { ...state.testResults }
    delete rest[name]
    state.testResults = rest
    state.keysMessage = { ...state.keysMessage, [name]: '' }
    state.testing = name
    try {
      state.testResults = { ...state.testResults, [name]: await deps.testCredential(name) }
    } catch (error) {
      refuseWrite(name, error, 'Could not test this credential.')
    } finally {
      state.testing = null
    }
  }

  function open(tab: 'sources' | 'keys' = 'sources', focus: string | null = null): void {
    state.tab = tab
    state.focus = focus
    state.isOpen = true
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
    saveLlm,
    saveCredential,
    clearLlmOverride,
    testCredential,
    open,
    close,
    updateProfile,
  })
}

/** Turn an API refusal into the error the controller explains inline. */
function refusal(error: unknown, status: number, fallback: string): SettingsRequestError {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  return new SettingsRequestError(typeof detail === 'string' ? detail : fallback, status)
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
    async listCredentials(): Promise<unknown> {
      const result = await listCredentialsApiV1SettingsCredentialsGet()
      if (result.data === undefined) {
        throw new SettingsRequestError('Could not load credentials.', (result.response?.status ?? 0))
      }
      return result.data
    },
    async saveLlm(input): Promise<unknown> {
      const result = await saveLlmCredentialsApiV1SettingsCredentialsLlmPut({
        body: { api_key: input.apiKey, base_url: input.baseUrl, model: input.model },
      })
      if (result.data === undefined) {
        throw refusal(result.error, (result.response?.status ?? 0), 'Could not save the LLM settings.')
      }
      return result.data
    },
    async saveCredential(name, value): Promise<unknown> {
      const result = await saveCredentialApiV1SettingsCredentialsNamePut({
        path: { name },
        body: { value },
      })
      if (result.data === undefined) {
        throw refusal(result.error, (result.response?.status ?? 0), 'Could not save this credential.')
      }
      return result.data
    },
    async deleteLlm(): Promise<void> {
      const result = await deleteLlmCredentialsApiV1SettingsCredentialsLlmDelete()
      if ((result.response?.status ?? 0) >= 400) {
        throw refusal(result.error, (result.response?.status ?? 0), 'Could not clear the saved key.')
      }
    },
    async deleteCredential(name): Promise<void> {
      const result = await deleteCredentialApiV1SettingsCredentialsNameDelete({ path: { name } })
      if ((result.response?.status ?? 0) >= 400) {
        throw refusal(result.error, (result.response?.status ?? 0), 'Could not clear the saved key.')
      }
    },
    async testCredential(name): Promise<CredentialTestOutcome> {
      const result = await testCredentialApiV1SettingsCredentialsNameTestPost({
        path: { name },
      })
      if (result.data === undefined) {
        throw refusal(result.error, (result.response?.status ?? 0), 'Could not test this credential.')
      }
      return { result: result.data.result, reason: result.data.reason }
    },
    async saveLanguage(language): Promise<void> {
      await saveOutputLanguageApiV1SettingsLanguagePut({
        body: { language: language as OutputLanguage },
      })
    },
  }
}

/**
 * Bind the controller to a Pinia setup store. The controller returns one reactive
 * object, but a setup store only keeps returned refs live: plain fields like
 * `isOpen` would be copied once and never update. `toRefs` points each field at
 * the controller, so the dialog, its tab and its focus follow the store.
 */
export function toSettingsStore(controller: ReturnType<typeof createSettingsController>) {
  const {
    load,
    save,
    saveLlm,
    saveCredential,
    clearLlmOverride,
    testCredential,
    open,
    close,
    updateProfile,
  } = controller
  return {
    ...toRefs(controller),
    load,
    save,
    saveLlm,
    saveCredential,
    clearLlmOverride,
    testCredential,
    open,
    close,
    updateProfile,
  }
}

export const useSettingsStore = defineStore('settings', () =>
  toSettingsStore(createSettingsController(defaultSettingsDeps())),
)
