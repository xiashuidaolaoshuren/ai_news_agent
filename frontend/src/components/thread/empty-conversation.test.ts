import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import EmptyConversation from '@/components/thread/EmptyConversation.vue'

/** The hidden-source flag is read at render time, so a test can flip it. */
const flags = vi.hoisted(() => ({ showBilibili: false }))

vi.mock('@/lib/features', () => ({
  get SHOW_BILIBILI() {
    return flags.showBilibili
  },
}))

afterEach(() => {
  flags.showBilibili = false
})

function orbitLogos(wrapper: ReturnType<typeof mount>): number {
  return wrapper.findAll('.orbit > span').length
}

describe('EmptyConversation', () => {
  it('shows the orbit without the hidden source', () => {
    const wrapper = mount(EmptyConversation)

    expect(orbitLogos(wrapper)).toBe(4)
  })

  it('shows the hidden source again when the flag is on', () => {
    flags.showBilibili = true
    const wrapper = mount(EmptyConversation)

    expect(orbitLogos(wrapper)).toBe(5)
  })

  it('offers the default digest first, then the prototype suggestions', async () => {
    const wrapper = mount(EmptyConversation)

    await wrapper.get('[data-od-id="suggestion-1"]').trigger('click')

    expect(wrapper.emitted('suggest')).toEqual([["Digest today's AI news"]])
    expect(wrapper.get('[data-od-id="suggestion-2"]').text()).toBe(
      'What shipped in open-weight models this week?',
    )
  })
})
