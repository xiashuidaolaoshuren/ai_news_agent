import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import ChatHead from '@/components/shell/ChatHead.vue'

beforeEach(() => {
  setActivePinia(createPinia())
})

function mountHead(props: { loading?: boolean; loadFailed?: boolean } = {}) {
  return mount(ChatHead, {
    props: { histOpen: false, loading: false, loadFailed: false, ...props },
  })
}

describe('ChatHead meta', () => {
  it('names the loading and load-failed states the prototype shows', () => {
    expect(mountHead({ loading: true }).get('.meta').text()).toBe('Loading…')
    expect(mountHead({ loadFailed: true }).get('.meta').text()).toBe('Not loaded')
    expect(mountHead().get('.meta').text()).toBe('Empty')
  })
})

describe('ChatHead theme toggle', () => {
  it('draws both glyphs and lets the data-theme attribute pick one', () => {
    // The prototype swaps moon and sun in CSS, so the new snapshot already has
    // the right glyph and Vue never sits between the click and the reveal.
    const button = mountHead().get('.theme-btn')

    expect(button.find('.ic-moon').exists()).toBe(true)
    expect(button.find('.ic-sun').exists()).toBe(true)
  })
})
