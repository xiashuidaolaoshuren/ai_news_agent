import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SourceSettings from '@/components/settings/SourceSettings.vue'
import type { SourceProfileVm } from '@/vm/settings'

const PROFILES: SourceProfileVm[] = [
  { name: 'juya', hidden: false, itemCount: 5 },
  {
    name: 'github',
    hidden: false,
    itemCount: 5,
    keywords: ['agent', 'mcp'],
    minStars: 50,
    language: 'TypeScript',
  },
  { name: 'huggingface', hidden: false, itemCount: 5, pipelineTag: 'text-generation' },
  { name: 'openrouter', hidden: false, itemCount: 5, freeOnly: false },
  { name: 'zhihu', hidden: false, itemCount: 5 },
  { name: 'bilibili', hidden: true },
]

function mountSettings(
  overrides: Partial<{
    language: 'source_default' | 'en' | 'zh-CN'
    profiles: SourceProfileVm[]
    githubAuthError: boolean
  }> = {},
) {
  return mount(SourceSettings, {
    props: {
      language: overrides.language ?? 'source_default',
      profiles: overrides.profiles ?? PROFILES,
      fieldErrors: {},
      githubAuthError: overrides.githubAuthError ?? false,
    },
  })
}

function emittedProfile(wrapper: ReturnType<typeof mountSettings>, name: string) {
  const events = wrapper.emitted('updateProfile') ?? []
  const match = events.filter((event) => (event[0] as SourceProfileVm).name === name)
  return match.at(-1)?.[0] as SourceProfileVm | undefined
}

describe('SourceSettings layout', () => {
  it('orders sections as the prototype does', () => {
    const wrapper = mountSettings()

    const ids = wrapper
      .findAll('[data-od-id^="settings-source-"]')
      .map((node) => node.attributes('data-od-id'))

    expect(ids).toEqual([
      'settings-source-juya',
      'settings-source-huggingface',
      'settings-source-openrouter',
      'settings-source-github',
      'settings-source-zhihu',
      'settings-source-bilibili',
    ])
  })

  it('explains the output language and the hidden Bilibili source', () => {
    const wrapper = mountSettings()

    expect(wrapper.text()).toContain(
      'Source default keeps each story in the language it was published in.',
    )
    expect(wrapper.get('[data-od-id="settings-source-bilibili"]').text()).toContain(
      'Not offered in the composer or the history source filter',
    )
    expect(wrapper.text()).toContain('Hidden from source selection')
  })

  it('warns that All can exceed 20 stories', () => {
    const withAll: SourceProfileVm[] = [
      { name: 'juya', hidden: false, itemCount: 'all' },
      ...PROFILES.slice(1),
    ]

    expect(mountSettings({ profiles: withAll }).find('[data-od-id="juya-all-warning"]').exists()).toBe(
      true,
    )
    expect(mountSettings().find('[data-od-id="juya-all-warning"]').exists()).toBe(false)
  })

  it('shows the GitHub auth warning with a jump to Keys', async () => {
    const wrapper = mountSettings({ githubAuthError: true })

    const warning = wrapper.get('[data-od-id="github-auth-warning"]')
    expect(warning.text()).toContain('Last check: authentication error.')
    await warning.get('button').trigger('click')
    expect(wrapper.emitted('gotoKeys')).toHaveLength(1)
  })
})

describe('SourceSettings GitHub fields', () => {
  it('shows the current minimum stars, language and keywords', () => {
    const wrapper = mountSettings()

    expect((wrapper.get('[data-od-id="github-min-stars"]').element as HTMLInputElement).value).toBe(
      '50',
    )
    expect(
      (wrapper.get('[data-od-id="github-language"]').element as HTMLSelectElement).value,
    ).toBe('TypeScript')
    expect(
      (wrapper.get('[data-od-id="github-keywords"]').element as HTMLInputElement).value,
    ).toBe('agent, mcp')
  })

  it('sends keywords as a trimmed list and language any as null', async () => {
    const wrapper = mountSettings()

    await wrapper.get('[data-od-id="github-keywords"]').setValue(' agent ,  mcp ,, tools ')
    expect(emittedProfile(wrapper, 'github')).toMatchObject({ keywords: ['agent', 'mcp', 'tools'] })

    await wrapper.get('[data-od-id="github-language"]').setValue('any')
    expect(emittedProfile(wrapper, 'github')).toMatchObject({ language: null })
  })

  it('sends minimum stars as a number', async () => {
    const wrapper = mountSettings()

    await wrapper.get('[data-od-id="github-min-stars"]').setValue('150')

    const profile = emittedProfile(wrapper, 'github')
    expect(profile?.name).toBe('github')
    expect(profile !== undefined && 'minStars' in profile ? profile.minStars : null).toBe(150)
  })
})

describe('SourceSettings Hugging Face pipeline', () => {
  it('shows the stored pipeline and sends any as null', async () => {
    const wrapper = mountSettings()

    const select = wrapper.get('[data-od-id="hf-pipeline"]')
    expect((select.element as HTMLSelectElement).value).toBe('text-generation')

    await select.setValue('any')
    const profile = emittedProfile(wrapper, 'huggingface')
    expect(profile !== undefined && 'pipelineTag' in profile ? profile.pipelineTag : 'missing').toBe(
      null,
    )
  })
})
