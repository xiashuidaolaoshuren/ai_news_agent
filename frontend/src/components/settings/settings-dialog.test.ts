import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import SettingsDialog, { type SettingsDialogVm } from '@/components/settings/SettingsDialog.vue'
import type { KeysVm, SourceProfileVm } from '@/vm/settings'

const KEYS: KeysVm = {
  readOnly: false,
  llmUnreadable: false,
  draft: {
    llmKey: '',
    llmUrl: '',
    llmModel: '',
    github: '',
    hf: '',
    zhihu: '',
    bilibiliSessdata: '',
    bilibiliBiliJct: '',
    bilibiliBuvid3: '',
  },
  rows: {},
  messages: {},
  results: {},
  testing: null,
  githubAuthError: false,
}

const PROFILES: SourceProfileVm[] = [
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
]

/** Attached dialogs share one document, so each test releases its own. */
const mounted: { unmount(): void }[] = []

afterEach(() => {
  for (const wrapper of mounted.splice(0)) {
    wrapper.unmount()
  }
})

function dialogVm(overrides: Partial<SettingsDialogVm> = {}): SettingsDialogVm {
  return {
    open: true,
    tab: 'sources',
    language: 'source_default',
    profiles: PROFILES,
    fieldErrors: {},
    saved: false,
    loadError: null,
    focus: null,
    keys: { ...KEYS },
    ...overrides,
  }
}

function mountDialog(
  overrides: Partial<{
    tab: 'sources' | 'keys'
    focus: string | null
    githubAuthError: boolean
  }> = {},
) {
  const wrapper = mount(SettingsDialog, {
    attachTo: document.body,
    props: {
      vm: {
        open: true,
        tab: overrides.tab ?? 'sources',
        language: 'source_default',
        profiles: PROFILES,
        fieldErrors: {},
        saved: false,
        loadError: null,
        focus: overrides.focus ?? null,
        keys: { ...KEYS, githubAuthError: overrides.githubAuthError ?? false },
      },
    },
  })
  mounted.push(wrapper)
  return wrapper
}

describe('SettingsDialog', () => {
  it('returns focus to whatever opened it when it closes', async () => {
    const opener = document.createElement('button')
    opener.id = 'settings-btn'
    document.body.append(opener)
    opener.focus()

    const wrapper = mount(SettingsDialog, {
      attachTo: document.body,
      props: { vm: { ...dialogVm(), open: true } },
    })
    mounted.push(wrapper)
    await flushPromises()

    await wrapper.setProps({ vm: { ...dialogVm(), open: false } })
    await flushPromises()

    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('switches tabs with the arrow keys', async () => {
    const wrapper = mountDialog()

    const sources = wrapper.get('[data-od-id="settings-tab-sources"]')
    sources.element.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
    )
    await flushPromises()

    expect(wrapper.emitted('setTab')).toEqual([['keys']])
  })

  it('closes on Escape from inside the dialog', async () => {
    const wrapper = mountDialog()

    wrapper.get('[data-od-id="settings-dialog"]').element.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    )
    await flushPromises()

    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('lists every source on the Sources tab, including hidden Bilibili', () => {
    const wrapper = mountDialog()

    expect(wrapper.get('[data-od-id="settings-dialog"]').attributes('role')).toBe('dialog')
    expect(wrapper.get('[data-od-id="settings-tab-sources"]').attributes('aria-selected')).toBe(
      'true',
    )
    for (const name of ['juya', 'github', 'huggingface', 'openrouter', 'zhihu', 'bilibili']) {
      expect(wrapper.find(`[data-od-id="settings-source-${name}"]`).exists()).toBe(true)
    }
    expect(wrapper.get('[data-od-id="settings-source-bilibili"]').text()).toContain(
      'Hidden from source selection',
    )
    expect(wrapper.find('[data-od-id="settings-output-language"]').exists()).toBe(true)
  })

  it('asks to save the current sources', async () => {
    const wrapper = mountDialog()

    await wrapper.get('[data-od-id="save-sources"]').trigger('click')

    expect(wrapper.emitted('save')).toHaveLength(1)
  })

  it('asks for the Keys tab and renders its panel there', async () => {
    const sources = mountDialog()
    await sources.get('[data-od-id="settings-tab-keys"]').trigger('click')
    expect(sources.emitted('setTab')).toEqual([['keys']])

    const keys = mountDialog({ tab: 'keys' })
    expect(keys.get('[data-od-id="settings-tab-keys"]').attributes('aria-selected')).toBe('true')
    expect(keys.find('[data-od-id="keys-llm-group"]').exists()).toBe(true)
    expect(keys.text()).toContain('Secrets are never shown after saving.')
    expect(keys.find('[data-od-id="save-sources"]').exists()).toBe(false)
  })

  it('scrolls to, flashes and focuses the source a gear asked for', async () => {
    const wrapper = mountDialog({ focus: 'github' })
    await flushPromises()

    const section = wrapper.get('#set-github')
    expect(section.classes()).toContain('hl')
    expect((document.activeElement as HTMLElement | null)?.tagName).toBe('INPUT')
    expect(section.get('input').element).toBe(document.activeElement)
    expect(wrapper.emitted('focusDone')).toHaveLength(1)

    wrapper.unmount()
  })

  it('focuses the key row a Keys jump asked for', async () => {
    const wrapper = mountDialog({ tab: 'keys', focus: 'github' })
    await flushPromises()

    expect(wrapper.get('[data-od-id="key-row-github"]').classes()).toContain('hl')
    expect((document.activeElement as HTMLElement | null)?.id).toBe('key-github')
    expect(wrapper.emitted('focusDone')).toHaveLength(1)

    wrapper.unmount()
  })

  it('jumps from the GitHub auth warning to the Keys row', async () => {
    const wrapper = mountDialog({ githubAuthError: true })
    await flushPromises()

    const warning = wrapper.get('[data-od-id="github-auth-warning"]')
    await warning.get('button').trigger('click')

    expect(wrapper.emitted('gotoKeys')).toHaveLength(1)
  })

  it('puts focus on the open tab when no section is asked for', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(document.activeElement?.id).toBe('tab-sources')
    expect(wrapper.emitted('focusDone')).toBeUndefined()

    wrapper.unmount()
  })
})
