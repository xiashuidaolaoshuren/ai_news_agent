import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MarkdownReply from '@/components/thread/MarkdownReply.vue'

/** The reply elements carry the `.caret` the reveal leaves at the cut. */
function caret(wrapper: ReturnType<typeof mount>): boolean {
  return wrapper.find('.caret').exists()
}

describe('MarkdownReply', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders the whole reply at once when it is not streaming', () => {
    const wrapper = mount(MarkdownReply, { props: { text: 'Alpha beta gamma' } })

    expect(wrapper.text()).toBe('Alpha beta gamma')
    expect(caret(wrapper)).toBe(false)
  })

  it('reveals the reply word by word while it streams', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const wrapper = mount(MarkdownReply, {
      props: { text: 'Alpha beta gamma delta', streaming: true },
    })

    expect(wrapper.text()).toBe('')
    expect(caret(wrapper)).toBe(true)

    await vi.advanceTimersByTimeAsync(70)
    await nextTick()
    expect(wrapper.text()).toBe('Alpha beta')

    await vi.advanceTimersByTimeAsync(70)
    await nextTick()
    expect(wrapper.text()).toBe('Alpha beta gamma')
  })

  it('drains the rest and hands the transcript back when the stream ends', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const wrapper = mount(MarkdownReply, {
      props: { text: 'Alpha beta gamma delta', streaming: true },
    })

    await vi.advanceTimersByTimeAsync(70)
    await wrapper.setProps({ ended: true })

    await vi.advanceTimersByTimeAsync(70)
    await vi.advanceTimersByTimeAsync(70)
    await nextTick()

    expect(wrapper.text()).toBe('Alpha beta gamma delta')
    expect(caret(wrapper)).toBe(false)
    expect(wrapper.emitted('revealed')).toHaveLength(1)
  })

  it('hands the transcript back when it unmounts mid-reveal', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const wrapper = mount(MarkdownReply, {
      props: { text: 'Alpha beta gamma delta', streaming: true },
    })

    wrapper.unmount()

    expect(wrapper.emitted('revealed')).toHaveLength(1)
  })
})
