import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import NoEligibleResults from '@/components/thread/NoEligibleResults.vue'
import type { CollectionVm, RepeatVm } from '@/vm/session'

const REPEAT: RepeatVm = {
  userMessageId: 4,
  text: 'AI agents this week',
  summary: 'GitHub · 5 per source · this week',
  sources: ['github'],
  perSource: 5,
}

function collection(over: Partial<CollectionVm> = {}): CollectionVm {
  return {
    outcome: 'no_eligible',
    sources: ['github'],
    topic: 'AI agents',
    timeframe: 'this_week',
    failedSource: null,
    reason: null,
    ...over,
  }
}

const CATALOG = [
  { name: 'juya', label: 'Juya', kind: 'juya' as const },
  { name: 'huggingface', label: 'Hugging Face', kind: 'huggingface' as const },
]

describe('NoEligibleResults', () => {
  it('names the timeframe instead of its raw token', () => {
    const wrapper = mount(NoEligibleResults, {
      props: { collection: collection(), repeat: REPEAT, catalog: CATALOG },
    })

    const text = wrapper.text()
    expect(text).toContain('this week')
    expect(text).not.toContain('this_week')
    expect(text).not.toContain('It runs')
    expect(wrapper.get('.help').text()).toBe('Try another source for AI agents this week.')
    expect(wrapper.findAll('p')[0]!.text()).toBe('GitHub was checked, and none of its stories from this week match AI agents.')
  })

  it('leaves an unknown timeframe as stored', () => {
    const wrapper = mount(NoEligibleResults, {
      props: { collection: collection({ timeframe: 'since tuesday' }), repeat: REPEAT, catalog: CATALOG },
    })

    expect(wrapper.text()).toContain('since tuesday')
  })
})
