import { createPinia, defineStore, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  createSettingsController,
  toSettingsStore,
  type SettingsDeps,
} from '@/stores/settings'

const PROFILES = {
  sources: [
    { name: 'juya', hidden: false, item_count: 5 },
    {
      name: 'github',
      hidden: false,
      item_count: 5,
      keywords: [],
      min_stars: 0,
      language: null,
    },
    { name: 'huggingface', hidden: false, item_count: 5, pipeline_tag: null },
    { name: 'openrouter', hidden: false, item_count: 5, free_only: false },
    { name: 'zhihu', hidden: false, item_count: 5 },
    { name: 'bilibili', hidden: true },
  ],
}

const CREDENTIALS = { secret_key_configured: true, credentials: [] }

function deps(): SettingsDeps {
  return {
    listProfiles: async () => PROFILES,
    getLanguage: async () => 'source_default',
    saveProfile: async () => {},
    saveLanguage: async () => {},
    listCredentials: async () => CREDENTIALS,
    saveLlm: async () => CREDENTIALS,
    saveCredential: async () => CREDENTIALS,
    deleteLlm: async () => {},
    deleteCredential: async () => {},
    testCredential: async () => ({ result: 'ok', reason: '' }),
  }
}

const useTestSettings = defineStore('test-settings', () =>
  toSettingsStore(createSettingsController(deps())),
)

describe('settings Pinia store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('opens the dialog through the store, not only the controller', async () => {
    const store = useTestSettings()

    store.open('sources', 'github')
    await new Promise((resolve) => {
      setTimeout(resolve, 0)
    })

    expect(store.isOpen).toBe(true)
    expect(store.tab).toBe('sources')
    expect(store.focus).toBe('github')
    expect(store.draft.profiles).toHaveLength(6)
  })

  it('keeps the dialog fields writable from outside the controller', () => {
    const store = useTestSettings()

    store.tab = 'keys'
    store.focus = 'github'

    expect(store.tab).toBe('keys')
    expect(store.focus).toBe('github')

    store.close()
    expect(store.isOpen).toBe(false)
  })

  it('shows a save outcome the controller recorded', async () => {
    const store = useTestSettings()
    await store.load()
    store.draft.language = 'en'

    await store.save()

    expect(store.saved).toBe(true)
    expect(store.language).toBe('en')
  })

  it('shows a load error the controller recorded', async () => {
    const useFailing = defineStore('test-settings-failing', () =>
      toSettingsStore(
        createSettingsController({
          ...deps(),
          listProfiles: async () => {
            throw new Error('backend down')
          },
        }),
      ),
    )
    const store = useFailing()

    await store.load()

    expect(store.loadError).toBe('backend down')
  })
})
