import { describe, expect, it } from 'vitest'

import type { HistorySearchMatchOut, SessionSearchHitOut } from '@/api/generated/types.gen'
import { toHistoryMatchVm, toSessionHitVm } from '@/vm'

describe('toSessionHitVm', () => {
  it('maps a title match', () => {
    const hit: SessionSearchHitOut = {
      session_id: 's1',
      title: 'Open models & agent tools',
      updated_at: '2026-10-01T20:09:00',
      match_kind: 'title',
      message_id: null,
      excerpt: 'Open models & agent tools',
    }

    expect(toSessionHitVm(hit)).toEqual({
      sessionId: 's1',
      title: 'Open models & agent tools',
      matchKind: 'title',
      excerpt: 'Open models & agent tools',
      updatedAt: '2026-10-01T20:09:00',
    })
  })

  it('names an untitled session and keeps the message match kind', () => {
    const vm = toSessionHitVm({
      session_id: 's2',
      title: null,
      updated_at: '2026-09-21T09:40:00',
      match_kind: 'assistant',
      message_id: 42,
      excerpt: 'A GGUF quant stores lower precision weights.',
    })

    expect(vm.title).toBe('New conversation')
    expect(vm.matchKind).toBe('assistant')
  })

  it('turns a blank excerpt into null', () => {
    const vm = toSessionHitVm({
      session_id: 's3',
      title: 'T',
      updated_at: '2026-09-21T09:40:00',
      match_kind: 'user',
      message_id: 7,
      excerpt: '   ',
    })

    expect(vm.excerpt).toBeNull()
  })
})

describe('toHistoryMatchVm', () => {
  function match(overrides: Partial<HistorySearchMatchOut> = {}): HistorySearchMatchOut {
    return {
      ref: { token: 'd15r9', digest_id: 15, run_id: 4, entry_id: 9, rank: 9 },
      generated_at: '2026-10-01T20:04:00',
      source_kind: 'huggingface',
      title: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      url: 'https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      excerpt: 'GGUF quant of Qwen-Image-2.1 · trending 816.',
      score: 12.5,
      topics: ['Model releases'],
      ...overrides,
    }
  }

  it('maps the token, date, source, and topics', () => {
    expect(toHistoryMatchVm(match())).toEqual({
      token: 'd15r9',
      digestId: 15,
      rank: 9,
      dateLabel: '2026-10-01',
      sourceKind: 'huggingface',
      label: 'Hugging Face',
      title: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      url: 'https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      host: 'huggingface.co',
      excerpt: 'GGUF quant of Qwen-Image-2.1 · trending 816.',
      topics: ['Model releases'],
    })
  })

  it('defaults missing topics, excerpt, and rank to safe values', () => {
    const vm = toHistoryMatchVm(
      match({
        excerpt: null,
        topics: undefined,
        ref: { token: 'd12r1', digest_id: 12, run_id: 3, entry_id: 1, rank: 1 },
      }),
    )

    expect(vm.topics).toEqual([])
    expect(vm.excerpt).toBeNull()
    expect(vm.rank).toBe(1)
  })

  it('drops a non-http url and its host', () => {
    const vm = toHistoryMatchVm(match({ url: 'javascript:alert(1)' }))

    expect(vm.url).toBeNull()
    expect(vm.host).toBeNull()
  })
})
