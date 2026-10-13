import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import Composer from '@/components/composer/Composer.vue'
import { toComposerVm, type ComposerVmInput } from '@/vm/composer'

/** The prototype's own catalog order, through the real mapper. */
function vm(overrides: Partial<ComposerVmInput> = {}) {
  return toComposerVm({
    text: '',
    sources: [
      { name: 'juya', label: 'Juya', kind: 'juya', default: true },
      { name: 'github', label: 'GitHub', kind: 'github', default: false },
    ],
    selected: ['juya'],
    count: '5',
    errors: {},
    busy: false,
    notice: 'none',
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

describe('composer busy state', () => {
  it('disables the sources, the stepper and Send, and offers Cancel', async () => {
    const wrapper = mount(Composer, { props: { vm: vm({ busy: true, notice: 'running' }) } })

    expect(wrapper.get('[data-od-id="send-button"]').attributes('disabled')).toBeDefined()
    expect(
      wrapper
        .findAll('[data-od-id="source-checkboxes"] input')
        .every((input) => input.attributes('disabled') !== undefined),
    ).toBe(true)
    expect(wrapper.get('#per-n').attributes('disabled')).toBeDefined()
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
            errors: { text: 'Type a question or topic first.', count: 'Items per source must be a whole number from 1 to 20.' },
          }),
        },
      },
    )

    expect(wrapper.get('[data-od-id="validation-errors"]').findAll('.err-msg')).toHaveLength(2)
  })
})
