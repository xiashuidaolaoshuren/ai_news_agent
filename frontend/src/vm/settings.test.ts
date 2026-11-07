import { describe, expect, it } from 'vitest'

import { toSourceProfilesVm } from '@/vm/settings'

/** Shape of `GET /api/v1/settings/sources`, which the generated client types as unknown. */
const PROFILES = {
  sources: [
    { name: 'juya', hidden: false, item_count: 'all' },
    {
      name: 'github',
      hidden: false,
      item_count: 5,
      keywords: ['llm'],
      min_stars: 10,
      language: 'python',
    },
    {
      name: 'huggingface',
      hidden: false,
      item_count: 5,
      pipeline_tag: 'text-generation',
    },
    { name: 'openrouter', hidden: false, item_count: 5, free_only: true },
    { name: 'zhihu', hidden: false, item_count: 8 },
    { name: 'bilibili', hidden: true },
  ],
}

describe('toSourceProfilesVm', () => {
  it('rejects a payload that is not a profile list', () => {
    expect(() => toSourceProfilesVm(null)).toThrow(/profile/)
    expect(() => toSourceProfilesVm({ sources: 'nope' })).toThrow(/profile/)
    expect(() => toSourceProfilesVm({ sources: [{ name: 'reddit' }] })).toThrow(/reddit/)
  })

  it('maps every source profile, including hidden Bilibili and Juya all', () => {
    expect(toSourceProfilesVm(PROFILES)).toEqual([
      { name: 'juya', hidden: false, itemCount: 'all' },
      {
        name: 'github',
        hidden: false,
        itemCount: 5,
        keywords: ['llm'],
        minStars: 10,
        language: 'python',
      },
      {
        name: 'huggingface',
        hidden: false,
        itemCount: 5,
        pipelineTag: 'text-generation',
      },
      { name: 'openrouter', hidden: false, itemCount: 5, freeOnly: true },
      { name: 'zhihu', hidden: false, itemCount: 8 },
      { name: 'bilibili', hidden: true },
    ])
  })
})
