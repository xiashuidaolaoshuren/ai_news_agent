import { describe, expect, it } from 'vitest'

import { createSettingsController, type SettingsDeps } from '@/stores/settings'

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

function deps(overrides: Partial<SettingsDeps> = {}): SettingsDeps {
  return {
    listProfiles: async () => PROFILES,
    getLanguage: async () => 'source_default',
    saveProfile: async () => {},
    saveLanguage: async () => {},
    readCountsSeen: () => false,
    writeCountsSeen: () => {},
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
