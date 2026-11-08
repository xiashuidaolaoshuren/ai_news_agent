import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import KeysPanel from '@/components/settings/KeysPanel.vue'
import type { KeysVm } from '@/vm/settings'

function keysVm(overrides: Partial<KeysVm> = {}): KeysVm {
  return {
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
    rows: {
      OPENAI_API_KEY: { status: 'app', last4: 'a1b2', version: 'v1' },
      OPENAI_BASE_URL: { status: 'env', last4: null, version: 'v1' },
      OPENAI_MODEL: { status: 'none', last4: null, version: null },
      GITHUB_TOKEN: { status: 'env', last4: '9f3c', version: 'v1' },
      HUGGINGFACE_TOKEN: { status: 'none', last4: null, version: null },
      ZHIHU_ACCESS_SECRET: { status: 'env', last4: '4d2e', version: 'v1' },
      BILIBILI_SESSDATA: { status: 'none', last4: null, version: null },
      BILIBILI_BILI_JCT: { status: 'none', last4: null, version: null },
      BILIBILI_BUVID3: { status: 'none', last4: null, version: null },
    },
    messages: {},
    results: {},
    testing: null,
    githubAuthError: false,
    ...overrides,
  }
}

describe('KeysPanel', () => {
  it('shows status and last4 but never a stored value', () => {
    const wrapper = mount(KeysPanel, { props: { vm: keysVm() } })

    expect(wrapper.text()).toContain('Saved in app')
    expect(wrapper.text()).toContain('…a1b2')
    expect(wrapper.text()).toContain('Environment')
    expect(wrapper.text()).toContain('Not set')
    expect(wrapper.text()).toContain('Fields are write-only')
    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBeGreaterThan(0)
    expect(inputs.every((input) => (input.element as HTMLInputElement).value === '')).toBe(true)
  })

  it('disables every write in read-only mode and explains the missing secret key', () => {
    const wrapper = mount(KeysPanel, {
      props: { vm: keysVm({ readOnly: true }) },
    })

    expect(wrapper.find('[data-od-id="keys-read-only"]').exists()).toBe(true)
    expect(
      wrapper.findAll('input').every((input) => (input.element as HTMLInputElement).disabled),
    ).toBe(true)
    expect(
      wrapper.findAll('button').filter((button) => button.text() === 'Save').length,
    ).toBeGreaterThan(0)
    expect(
      wrapper
        .findAll('button')
        .filter((button) => /Save|Test connection/.test(button.text()))
        .every((button) => (button.element as HTMLButtonElement).disabled),
    ).toBe(true)
  })

  it('shows the unreadable override with a clear action', async () => {
    const wrapper = mount(KeysPanel, {
      props: { vm: keysVm({ llmUnreadable: true }) },
    })

    expect(wrapper.find('[data-od-id="keys-unreadable-override"]').exists()).toBe(true)
    await wrapper.find('[data-od-id="clear-override"]').trigger('click')

    expect(wrapper.emitted('clearOverride')).toHaveLength(1)
  })

  it('saves the LLM triple and tests the LLM key', async () => {
    const wrapper = mount(KeysPanel, { props: { vm: keysVm() } })

    await wrapper.find('[data-od-id="save-llm"]').trigger('click')
    await wrapper.find('[data-od-id="test-llm"]').trigger('click')

    expect(wrapper.emitted('saveLlm')).toHaveLength(1)
    expect(wrapper.emitted('test')).toEqual([['OPENAI_API_KEY']])
    expect(wrapper.text()).toContain('The check may incur a small charge')
  })

  it('shows a test result as the sanitized reason', () => {
    const wrapper = mount(KeysPanel, {
      props: {
        vm: keysVm({
          results: {
            OPENAI_API_KEY: { result: 'auth_error', reason: 'The provider rejected the key.' },
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Test failed: The provider rejected the key.')
  })

  it('replaces the test hint with the result, as the prototype does', () => {
    const before = mount(KeysPanel, { props: { vm: keysVm() } })
    expect(before.text()).toContain(
      'Sends one short request to the model. The check may incur a small charge.',
    )

    const after = mount(KeysPanel, {
      props: {
        vm: keysVm({ results: { OPENAI_API_KEY: { result: 'ok', reason: '' } } }),
      },
    })
    expect(after.text()).toContain('Connection OK. The model replied.')
    expect(after.text()).not.toContain('Sends one short request to the model.')
  })

  it('saves each source credential on its own and keeps Bilibili editable', async () => {
    const wrapper = mount(KeysPanel, { props: { vm: keysVm() } })

    await wrapper
      .find('[data-od-id="key-row-github"] button')
      .trigger('click')
    await wrapper.find('[data-od-id="key-row-bilibiliSessdata"] button').trigger('click')

    expect(wrapper.emitted('saveKey')).toEqual([['github'], ['bilibiliSessdata']])
    expect(
      wrapper.findAll('[data-od-id^="key-row-bilibili"]').every(
        (row) => !row.find('[data-od-id="test-BILIBILI_SESSDATA"]').exists(),
      ),
    ).toBe(true)
  })

  it('jumps to the GitHub source section only when the last check failed', async () => {
    const ok = mount(KeysPanel, { props: { vm: keysVm() } })
    expect(ok.find('[data-od-id="github-auth-link"]').exists()).toBe(false)

    const failed = mount(KeysPanel, {
      props: { vm: keysVm({ githubAuthError: true }) },
    })
    await failed.find('[data-od-id="github-auth-link"]').trigger('click')
    expect(failed.emitted('gotoSource')).toEqual([['github']])
  })

  it('reports typed values as the draft changes', async () => {
    const wrapper = mount(KeysPanel, { props: { vm: keysVm() } })

    await wrapper.find('#key-github').setValue('ghp_new')

    expect(wrapper.emitted('updateDraft')).toEqual([['github', 'ghp_new']])
  })
})
