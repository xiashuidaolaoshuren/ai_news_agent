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
