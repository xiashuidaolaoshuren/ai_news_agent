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
    { name: 'llm', status: 'env', last4: 'a1b2', version: 'v1' },
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

  it('refuses a count outside 1 to 50 before any request, and points at the section', async () => {
    const saved: string[] = []
    const controller = createSettingsController(
      deps({
        saveProfile: async (name) => {
          saved.push(name)
        },
      }),
    )
    await controller.load()
    const juya = controller.draft.profiles.find((profile) => profile.name === 'juya')
    const github = controller.draft.profiles.find((profile) => profile.name === 'github')
    if (juya?.name !== 'juya' || github?.name !== 'github') {
      throw new Error('expected juya and github drafts')
    }
    // Juya keeps its stored count while All is on, so only the other sources are checked.
    juya.itemCount = 'all'
    github.itemCount = 51

    await controller.save()

    expect(saved).toEqual([])
    expect(controller.fieldErrors.github).toBe(
      'Item count must be a whole number from 1 to 50.',
    )
    expect(controller.fieldErrors.juya).toBeUndefined()
    expect(controller.saved).toBe(false)
    expect(controller.focus).toBe('github')
  })

  it('refuses a fractional or unreadable count', async () => {
    const saved: string[] = []
    const controller = createSettingsController(
      deps({
        saveProfile: async (name) => {
          saved.push(name)
        },
      }),
    )
    await controller.load()
    const zhihu = controller.draft.profiles.find((profile) => profile.name === 'zhihu')
    if (zhihu?.name !== 'zhihu') {
      throw new Error('expected a zhihu draft')
    }

    zhihu.itemCount = Number.NaN
    await controller.save()
    expect(saved).toEqual([])
    expect(controller.fieldErrors.zhihu).toBe(
      'Item count must be a whole number from 1 to 50.',
    )

    zhihu.itemCount = 2.5
    await controller.save()
    expect(saved).toEqual([])
    expect(controller.fieldErrors.zhihu).toBe(
      'Item count must be a whole number from 1 to 50.',
    )
  })

  it('sends the GitHub filters and the Hugging Face pipeline', async () => {
    const saved: { name: string; body: Record<string, unknown> }[] = []
    const controller = createSettingsController(
      deps({
        saveProfile: async (name, body) => {
          saved.push({ name, body })
        },
      }),
    )
    await controller.load()
    const github = controller.draft.profiles.find((profile) => profile.name === 'github')
    const hf = controller.draft.profiles.find((profile) => profile.name === 'huggingface')
    if (github?.name !== 'github' || hf?.name !== 'huggingface') {
      throw new Error('expected github and huggingface drafts')
    }
    github.keywords = ['agent', 'mcp']
    github.minStars = 50
    github.language = 'TypeScript'
    hf.pipelineTag = 'text-generation'

    await controller.save()

    expect(saved).toEqual([
      {
        name: 'github',
        body: {
          item_count: 5,
          keywords: ['agent', 'mcp'],
          min_stars: 50,
          language: 'TypeScript',
        },
      },
      { name: 'huggingface', body: { item_count: 5, pipeline_tag: 'text-generation' } },
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
    // A count the client accepts, so the refusal comes from the API as intended.
    juya.itemCount = 7

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
    expect(controller.keysMessage.llm).toBe('Saved in app.')
  })

  it('clears the saved LLM key and reloads the statuses', async () => {
    let payload = {
      ...CREDENTIALS,
      credentials: CREDENTIALS.credentials.map((row) =>
        row.name === 'llm' ? { ...row, status: 'unreadable' } : row,
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
    expect(controller.keysMessage.llm).toBe(
      'Saved key cleared. Using OPENAI_API_KEY from the environment.',
    )
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
    expect(controller.keysMessage.github).toBe(
      'Saved in app. The value won’t be shown again.',
    )
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
      'Enter a value to save.',
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
