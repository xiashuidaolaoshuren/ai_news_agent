import { describe, expect, it } from 'vitest'

import {
  SettingsRequestError,
  createSettingsController,
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

const CREDENTIALS = {
  secret_key_configured: true,
  credentials: [
    { name: 'OPENAI_API_KEY', status: 'env', last4: 'a1b2', version: 'v1' },
    { name: 'OPENAI_BASE_URL', status: 'unset', last4: null, version: null },
    { name: 'OPENAI_MODEL', status: 'unset', last4: null, version: null },
    { name: 'GITHUB_TOKEN', status: 'ui', last4: '9f3c', version: 'v1' },
    { name: 'HUGGINGFACE_TOKEN', status: 'unset', last4: null, version: null },
    { name: 'ZHIHU_ACCESS_SECRET', status: 'env', last4: '4d2e', version: 'v1' },
    { name: 'BILIBILI_SESSDATA', status: 'unset', last4: null, version: null },
    { name: 'BILIBILI_BILI_JCT', status: 'unset', last4: null, version: null },
    { name: 'BILIBILI_BUVID3', status: 'unset', last4: null, version: null },
  ],
}

function deps(overrides: Partial<SettingsDeps> = {}): SettingsDeps {
  return {
    listProfiles: async () => PROFILES,
    getLanguage: async () => 'source_default',
    saveProfile: async () => {},
    saveLanguage: async () => {},
    readCountsSeen: () => false,
    writeCountsSeen: () => {},
    listCredentials: async () => CREDENTIALS,
    saveLlm: async () => CREDENTIALS,
    saveCredential: async () => CREDENTIALS,
    deleteLlm: async () => {},
    deleteCredential: async () => {},
    testCredential: async () => ({ result: 'ok', reason: '' }),
    ...overrides,
  }
}

describe('createSettingsController', () => {
  it('fills the draft from the source profiles and the saved language', async () => {
    const controller = createSettingsController(
      deps({ getLanguage: async () => 'zh-CN' }),
    )

    await controller.load()

    expect(controller.language).toBe('zh-CN')
    expect(controller.draft).toEqual({
      language: 'zh-CN',
      profiles: [
        { name: 'juya', hidden: false, itemCount: 5 },
        {
          name: 'github',
          hidden: false,
          itemCount: 5,
          keywords: [],
          minStars: 0,
          language: null,
        },
        { name: 'huggingface', hidden: false, itemCount: 5, pipelineTag: null },
        { name: 'openrouter', hidden: false, itemCount: 5, freeOnly: false },
        { name: 'zhihu', hidden: false, itemCount: 5 },
        { name: 'bilibili', hidden: true },
      ],
    })
  })

  it('saves only profiles whose fields changed, in API field names', async () => {
    const saved: { name: string; body: Record<string, unknown> }[] = []
    const controller = createSettingsController(
      deps({
        saveProfile: async (name, body) => {
          saved.push({ name, body })
        },
      }),
    )
    await controller.load()
    const juya = controller.draft.profiles.find((profile) => profile.name === 'juya')
    const openrouter = controller.draft.profiles.find(
      (profile) => profile.name === 'openrouter',
    )
    if (juya?.name !== 'juya' || openrouter?.name !== 'openrouter') {
      throw new Error('expected juya and openrouter drafts')
    }
    juya.itemCount = 'all'
    openrouter.freeOnly = true

    await controller.save()

    expect(saved).toEqual([
      { name: 'juya', body: { item_count: 'all' } },
      { name: 'openrouter', body: { item_count: 5, free_only: true } },
    ])
  })

  it('sends zh-CN when the output language changes', async () => {
    const languages: string[] = []
    const controller = createSettingsController(
      deps({
        saveLanguage: async (language) => {
          languages.push(language)
        },
      }),
    )
    await controller.load()
    controller.draft.language = 'zh-CN'

    await controller.save()

    expect(languages).toEqual(['zh-CN'])
    expect(controller.language).toBe('zh-CN')
  })

  it('keeps the API message on the profile a save rejects', async () => {
    const message = "item_count must be 1-50 or 'all'"
    const controller = createSettingsController(
      deps({
        saveProfile: async (name) => {
          if (name === 'juya') {
            throw new Error(message)
          }
        },
      }),
    )
    await controller.load()
    const juya = controller.draft.profiles.find((profile) => profile.name === 'juya')
    if (juya?.name !== 'juya') {
      throw new Error('expected a juya draft')
    }
    juya.itemCount = 0

    await controller.save()

    expect(controller.fieldErrors.juya).toBe(message)
  })

  it('records the source a gear asks the dialog to open on', () => {
    const controller = createSettingsController(deps())

    controller.open('sources', 'github')

    expect(controller.isOpen).toBe(true)
    expect(controller.tab).toBe('sources')
    expect(controller.focus).toBe('github')
  })

  it('hides the count notice after it is dismissed once', () => {
    let seen = false
    const controller = createSettingsController(
      deps({
        readCountsSeen: () => seen,
        writeCountsSeen: () => {
          seen = true
        },
      }),
    )

    expect(controller.countsSeen).toBe(false)
    controller.dismissCounts()
    expect(seen).toBe(true)
    expect(controller.countsSeen).toBe(true)
  })
})

describe('createSettingsController keys', () => {
  it('fills the Keys rows from the credential statuses', async () => {
    const controller = createSettingsController(deps())

    await controller.load()

    expect(controller.credentials.rows.GITHUB_TOKEN).toEqual({
      status: 'app',
      last4: '9f3c',
      version: 'v1',
    })
    expect(controller.credentials.readOnly).toBe(false)
    expect(controller.keysDraft.github).toBe('')
  })

  it('saves the LLM key, base URL and model in one PUT and clears the fields', async () => {
    const calls: unknown[] = []
    const controller = createSettingsController(
      deps({
        saveLlm: async (input) => {
          calls.push(input)
          return CREDENTIALS
        },
      }),
    )
    await controller.load()
    controller.keysDraft.llmKey = 'sk-new'
    controller.keysDraft.llmUrl = 'https://api.example.com/v1'
    controller.keysDraft.llmModel = 'openai/gpt-x'

    await controller.saveLlm()

    expect(calls).toEqual([
      { apiKey: 'sk-new', baseUrl: 'https://api.example.com/v1', model: 'openai/gpt-x' },
    ])
    expect(controller.keysDraft.llmKey).toBe('')
    expect(controller.keysDraft.llmUrl).toBe('')
    expect(controller.keysDraft.llmModel).toBe('')
    expect(controller.keysMessage.llm).toBe('Saved.')
  })

  it('clears the saved LLM key and reloads the statuses', async () => {
    let payload = {
      ...CREDENTIALS,
      credentials: CREDENTIALS.credentials.map((row) =>
        row.name === 'OPENAI_API_KEY' ? { ...row, status: 'unreadable' } : row,
      ),
    }
    let cleared = 0
    const controller = createSettingsController(
      deps({
        listCredentials: async () => payload,
        deleteLlm: async () => {
          cleared += 1
          payload = CREDENTIALS
        },
      }),
    )
    await controller.load()
    expect(controller.credentials.llmUnreadable).toBe(true)

    await controller.clearLlmOverride()

    expect(cleared).toBe(1)
    expect(controller.credentials.llmUnreadable).toBe(false)
    expect(controller.keysMessage.llm).toBe('Cleared the saved key.')
  })

  it('saves one source credential with its own PUT and clears the input', async () => {
    const saves: [string, string][] = []
    const controller = createSettingsController(
      deps({
        saveCredential: async (name, value) => {
          saves.push([name, value])
          return CREDENTIALS
        },
      }),
    )
    await controller.load()
    controller.keysDraft.github = 'ghp_new'

    await controller.saveCredential('github')

    expect(saves).toEqual([['GITHUB_TOKEN', 'ghp_new']])
    expect(controller.keysDraft.github).toBe('')
    expect(controller.keysMessage.github).toBe('Saved.')
  })

  it('refuses to save an empty source credential', async () => {
    let calls = 0
    const controller = createSettingsController(
      deps({
        saveCredential: async () => {
          calls += 1
          return CREDENTIALS
        },
      }),
    )
    await controller.load()
    controller.keysDraft.github = '   '

    await controller.saveCredential('github')

    expect(calls).toBe(0)
    expect(controller.keysMessage.github).toBe(
      'Enter a new value to save this credential.',
    )
  })

  it('records the sanitized result of one credential test', async () => {
    const tested: string[] = []
    const controller = createSettingsController(
      deps({
        testCredential: async (name) => {
          tested.push(name)
          return { result: 'auth_error', reason: 'GitHub rejected the token (401).' }
        },
      }),
    )
    await controller.load()

    await controller.testCredential('GITHUB_TOKEN')

    expect(tested).toEqual(['GITHUB_TOKEN'])
    expect(controller.testResults.GITHUB_TOKEN).toEqual({
      result: 'auth_error',
      reason: 'GitHub rejected the token (401).',
    })
    expect(controller.testing).toBe(null)
  })

  it('refuses to save the LLM group without a new key', async () => {
    let calls = 0
    const controller = createSettingsController(
      deps({
        saveLlm: async () => {
          calls += 1
          return CREDENTIALS
        },
      }),
    )
    await controller.load()
    controller.keysDraft.llmModel = 'openai/gpt-x'

    await controller.saveLlm()

    expect(calls).toBe(0)
    expect(controller.keysMessage.llm).toBe(
      'Enter the API key to save the LLM settings. Saving never reuses the stored key.',
    )
  })

  it('switches the panel to read-only when a write is refused with 409', async () => {
    const controller = createSettingsController(
      deps({
        saveLlm: async () => {
          throw new SettingsRequestError('Encryption is not enabled on this backend.', 409)
        },
      }),
    )
    await controller.load()
    controller.keysDraft.llmKey = 'sk-new'

    await controller.saveLlm()

    expect(controller.credentials.readOnly).toBe(true)
    expect(controller.keysMessage.llm).toBe('Encryption is not enabled on this backend.')
  })

  it('marks the panel read-only when the backend has no secret key', async () => {
    const controller = createSettingsController(
      deps({ listCredentials: async () => ({ ...CREDENTIALS, secret_key_configured: false }) }),
    )

    await controller.load()

    expect(controller.credentials.readOnly).toBe(true)
  })
})
