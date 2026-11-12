import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EmptyConversation from '@/components/thread/EmptyConversation.vue'
import type { EntryKind } from '@/vm'

function orbitLogos(wrapper: ReturnType<typeof mount>): number {
  return wrapper.findAll('.orbit > span').length
}

/** The visible kinds the catalog reports, in its order. */
const KINDS: EntryKind[] = ['juya', 'huggingface', 'openrouter', 'github', 'zhihu']

describe('EmptyConversation', () => {
  it('shows one orbit logo per visible kind', () => {
    const wrapper = mount(EmptyConversation, { props: { kinds: KINDS } })

    expect(orbitLogos(wrapper)).toBe(5)
  })

  it('shows a restored hidden source when the catalog includes it', () => {
    const wrapper = mount(EmptyConversation, {
      props: { kinds: [...KINDS, 'bilibili'] },
    })

    expect(orbitLogos(wrapper)).toBe(6)
  })

  it('shows no orbit before the catalog loads', () => {
    const wrapper = mount(EmptyConversation, { props: { kinds: [] } })

    expect(orbitLogos(wrapper)).toBe(0)
  })

  it('offers the default digest first, then the prototype suggestions', async () => {
    const wrapper = mount(EmptyConversation, { props: { kinds: KINDS } })

    await wrapper.get('[data-od-id="suggestion-1"]').trigger('click')

    expect(wrapper.emitted('suggest')).toEqual([["Digest today's AI news"]])
    expect(wrapper.get('[data-od-id="suggestion-2"]').text()).toBe(
      'What shipped in open-weight models this week?',
    )
  })
})
