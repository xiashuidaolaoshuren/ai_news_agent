import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import Composer from '@/components/composer/Composer.vue'
import { toComposerVm, type ComposerVmInput } from '@/vm/composer'

/** The prototype's own catalog order, through the real mapper. */
function vm(overrides: Partial<ComposerVmInput> = {}) {
  return toComposerVm({
    text: '',
    sources: [
      { name: 'juya', label: 'Juya', kind: 'juya', default: true, health: 'unchecked' },
      {
        name: 'github',
        label: 'GitHub',
        kind: 'github',
        default: false,
        health: 'unchecked',
      },
    ],
    selected: ['juya'],
    errors: {},
    busy: false,
    notice: 'none',
    ref: null,
    countsSeen: true,
    ...overrides,
  })
}

describe('composer keyboard', () => {
  it('sends on Enter', async () => {
    const wrapper = mount(Composer, { props: { vm: vm() } })

    await wrapper.get('#msg').trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('send')).toHaveLength(1)
  })

  it('keeps Shift+Enter as a newline', async () => {
    const wrapper = mount(Composer, { props: { vm: vm() } })

    await wrapper.get('#msg').trigger('keydown', { key: 'Enter', shiftKey: true })

    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('ignores Enter while an IME composition is open', async () => {
    const wrapper = mount(Composer, { props: { vm: vm() } })

    wrapper
      .get('#msg')
      .element.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true }),
      )

    expect(wrapper.emitted('send')).toBeUndefined()
  })
})

describe('composer source counts', () => {
  it('has no per-source count stepper', () => {
    const wrapper = mount(Composer, { props: { vm: vm() } })

    expect(wrapper.find('#per-n').exists()).toBe(false)
    expect(wrapper.find('[data-od-id="items-per-source"]').exists()).toBe(false)
  })

  it('opens that source settings from its gear', async () => {
    const wrapper = mount(Composer, { props: { vm: vm() } })

    await wrapper.get('[data-od-id="source-settings-github"]').trigger('click')

    expect(wrapper.emitted('openSettings')).toEqual([['github']])
  })

  it('shows the global count notice until it is dismissed', async () => {
    const wrapper = mount(Composer, { props: { vm: vm({ countsSeen: false }) } })
    const notice = wrapper.get('[data-od-id="source-count-notice"]')

    expect(notice.text()).toContain(
      'New requests use the global source counts from Settings, initially 5 per source.',
    )
    await notice.get('[aria-label="Dismiss notice"]').trigger('click')
    expect(wrapper.emitted('dismissCounts')).toHaveLength(1)
  })
})

describe('composer busy state', () => {
  it('disables the sources and Send, and offers Cancel', async () => {
    const wrapper = mount(Composer, { props: { vm: vm({ busy: true, notice: 'running' }) } })

    expect(wrapper.get('[data-od-id="send-button"]').attributes('disabled')).toBeDefined()
    expect(
      wrapper
        .findAll('[data-od-id="source-checkboxes"] input')
        .every((input) => input.attributes('disabled') !== undefined),
    ).toBe(true)
    expect(wrapper.find('#per-n').exists()).toBe(false)
    expect(wrapper.find('[data-od-id="cancel-request"]').exists()).toBe(true)
    expect(wrapper.get('[data-od-id="busy-notice"]').text()).toContain(
      'You can draft your next message.',
    )
    // Drafting continues while the request runs, as the notice promises.
    expect(wrapper.get('#msg').attributes('disabled')).toBeUndefined()
  })

  it('shows the reconnect copy while polling a dropped stream', () => {
    const wrapper = mount(
      Composer,
      { props: { vm: vm({ busy: true, notice: 'reconnecting' }) } },
    )

    expect(wrapper.get('[data-od-id="busy-notice"]').text()).toContain(
      'Reconnecting to the running request',
    )
  })

  it('says the conversation did not load, and disables Send', () => {
    const wrapper = mount(Composer, { props: { vm: vm({ loadFailed: true }) } })

    const notice = wrapper.get('[data-od-id="load-failed-notice"]')
    expect(notice.attributes('role')).toBe('status')
    expect(notice.text()).toContain("This conversation didn't load. Retry above before sending.")

    const send = wrapper.get('[data-od-id="send-button"]')
    expect(send.attributes('disabled')).toBeDefined()
    expect(send.attributes('aria-disabled')).toBe('true')
  })

  it('names the Juya confirmation when a send waits on it', () => {
    const wrapper = mount(Composer, { props: { vm: vm({ confirmPending: true }) } })

    const notice = wrapper.get('[data-od-id="confirm-pending-notice"]')
    expect(notice.attributes('role')).toBe('alert')
    expect(notice.text()).toContain(
      'Not sent. Continue or cancel the Juya request above first.',
    )
  })

  it('reports that a cancelled confirmation left nothing behind', () => {
    const note = 'Cancelled. No digest was written, and your request is back in the composer.'
    const wrapper = mount(Composer, { props: { vm: vm({ confirmCancelled: note }) } })

    const notice = wrapper.get('[data-od-id="confirm-cancelled-notice"]')
    expect(notice.attributes('role')).toBe('status')
    expect(notice.text()).toContain(note)
    expect(notice.find('.ic').exists()).toBe(true)
  })

  it('offers Settings from the counts notice', async () => {
    const wrapper = mount(Composer, { props: { vm: vm({ countsSeen: false }) } })

    const note = wrapper.get('[data-od-id="source-count-notice"]')
    await note.get('button.link-btn').trigger('click')

    expect(wrapper.emitted('openSettings')).toEqual([[null]])
  })

  it('shows the blocked notice with no Cancel when the send was refused', () => {
    const wrapper = mount(Composer, { props: { vm: vm({ notice: 'blocked' }) } })

    expect(wrapper.get('[data-od-id="busy-blocked-notice"]').text()).toContain('Not sent.')
    expect(wrapper.find('[data-od-id="cancel-request"]').exists()).toBe(false)
  })

  it('lists one error per failing rule', () => {
    const wrapper = mount(
      Composer,
      {
        props: {
          vm: vm({
            errors: {
              text: 'Type a question or topic first.',
              sources: 'Select at least one source.',
            },
          }),
        },
      },
    )

    expect(wrapper.get('[data-od-id="validation-errors"]').findAll('.err-msg')).toHaveLength(2)
  })
})

describe('composer source health', () => {
  function healthVm(githubHealth: 'auth_error' | 'stale' | 'ok') {
    return vm({
      sources: [
        { name: 'juya', label: 'Juya', kind: 'juya', default: true, health: 'unchecked' },
        { name: 'github', label: 'GitHub', kind: 'github', default: false, health: githubHealth },
      ],
    })
  }

  it('marks the source whose last check failed and explains it', () => {
    const wrapper = mount(Composer, { props: { vm: healthVm('auth_error') } })

    const github = wrapper.get('[data-src="github"]').element.closest('.src-item')
    expect(github?.querySelector('.pip')).not.toBeNull()
    expect(github?.querySelector('.tip')?.textContent).toContain(
      'Last check: authentication error.',
    )
    const juya = wrapper.get('[data-src="juya"]').element.closest('.src-item')
    expect(juya?.querySelector('.pip')).toBeNull()
    expect(wrapper.get('[data-src="github"]').attributes('aria-describedby')).toBe(
      'src-tip-github',
    )
  })

  it('says health is unchecked since the credential changed', () => {
    const wrapper = mount(Composer, { props: { vm: healthVm('stale') } })

    expect(
      wrapper.get('[data-src="github"]').element.closest('.src-item')?.querySelector('.tip')
        ?.textContent,
    ).toContain('Not checked since update.')
  })

  it('shows no pip when the health is ok', () => {
    const wrapper = mount(Composer, { props: { vm: healthVm('ok') } })

    expect(
      wrapper.get('[data-src="github"]').element.closest('.src-item')?.querySelector('.pip'),
    ).toBeNull()
  })
})
