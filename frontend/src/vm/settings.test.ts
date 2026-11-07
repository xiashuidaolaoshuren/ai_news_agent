import { describe, expect, it } from 'vitest'

import { toCredentialsVm, toSourceProfilesVm } from '@/vm/settings'

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

describe('toCredentialsVm', () => {
  const PAYLOAD = {
    secret_key_configured: true,
    credentials: [
      { name: 'OPENAI_API_KEY', status: 'ui', last4: 'a1b2', version: 'v1' },
      { name: 'OPENAI_BASE_URL', status: 'env', last4: null, version: 'v1' },
      { name: 'OPENAI_MODEL', status: 'unset', last4: null, version: null },
      { name: 'GITHUB_TOKEN', status: 'env', last4: '9f3c', version: 'v1' },
      { name: 'HUGGINGFACE_TOKEN', status: 'unset', last4: null, version: null },
      { name: 'ZHIHU_ACCESS_SECRET', status: 'env', last4: '4d2e', version: 'v1' },
      { name: 'BILIBILI_SESSDATA', status: 'unset', last4: null, version: null },
      { name: 'BILIBILI_BILI_JCT', status: 'unset', last4: null, version: null },
      { name: 'BILIBILI_BUVID3', status: 'unset', last4: null, version: null },
    ],
  }

  it('maps each API status to the row state and keeps last4', () => {
    const vm = toCredentialsVm(PAYLOAD)
    expect(vm.rows.OPENAI_API_KEY).toEqual({
      status: 'app',
      last4: 'a1b2',
      version: 'v1',
    })
    expect(vm.rows.OPENAI_BASE_URL).toEqual({
      status: 'env',
      last4: null,
      version: 'v1',
    })
    expect(vm.rows.OPENAI_MODEL).toEqual({
      status: 'none',
      last4: null,
      version: null,
    })
  })

  it('keeps an unreadable credential distinct from an unset one', () => {
    const vm = toCredentialsVm({
      secret_key_configured: true,
      credentials: [
        { name: 'OPENAI_API_KEY', status: 'unreadable', last4: null, version: 'v2' },
        { name: 'GITHUB_TOKEN', status: 'unset', last4: null, version: null },
      ],
    })
    expect(vm.rows.OPENAI_API_KEY?.status).toBe('bad')
    expect(vm.rows.GITHUB_TOKEN?.status).toBe('none')
    expect(vm.llmUnreadable).toBe(true)
  })

  it('reads the read-only flag from the missing secret key', () => {
    expect(
      toCredentialsVm({ secret_key_configured: false, credentials: [] }).readOnly,
    ).toBe(true)
  })

  it('rejects a payload that is not a credential list', () => {
    expect(() => toCredentialsVm(null)).toThrow(/credential/)
    expect(() => toCredentialsVm({ credentials: 'nope' })).toThrow(/credential/)
  })
})
