import { describe, expect, it } from 'vitest'

import type {
  DigestEntryView,
  HistoryItemShowOut,
  HistorySearchMatchOut,
  HistorySearchResultOut,
  SessionSearchHitOut,
} from '@/api/generated/types.gen'
import {
  EMPTY_HISTORY_FILTERS,
  filterCount,
  historySourceOptions,
  toHistoryMatchVm,
  toHistoryQuery,
  toHistoryResultVm,
  toOpenedVm,
  toSessionHitVm,
  type HistoryFilters,
} from '@/vm'

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

describe('history filters', () => {
  function filters(overrides: Partial<HistoryFilters> = {}): HistoryFilters {
    return { ...EMPTY_HISTORY_FILTERS, ...overrides }
  }

  it('lists every source kind behind an all-sources option', () => {
    expect(historySourceOptions().map((option) => option.value)).toEqual([
      'all',
      'juya',
      'huggingface',
      'github',
      'zhihu',
      'bilibili',
    ])
    expect(historySourceOptions()[0]?.label).toBe('All sources')
  })

  it('makes no query while every filter is empty', () => {
    expect(toHistoryQuery(filters())).toBeNull()
    expect(toHistoryQuery(filters({ text: '   ' }))).toBeNull()
  })

  it('sends trimmed text with the result limit', () => {
    expect(toHistoryQuery(filters({ text: '  gguf quant  ' }))).toEqual({
      text: 'gguf quant',
      limit: 10,
    })
  })

  it('drops the all-sources option and translates the prototype alias', () => {
    expect(toHistoryQuery(filters({ source: 'all' }))).toBeNull()
    expect(toHistoryQuery(filters({ source: 'hf' }))).toEqual({
      sources: 'huggingface',
      limit: 10,
    })
    expect(toHistoryQuery(filters({ source: 'GitHub' }))).toEqual({
      sources: 'github',
      limit: 10,
    })
  })

  it('splits the free-text topic list into a csv', () => {
    expect(toHistoryQuery(filters({ topic: 'Model releases, Research & insight' }))).toEqual({
      topics: 'Model releases,Research & insight',
      limit: 10,
    })
  })

  it('maps From and To onto since and until', () => {
    expect(toHistoryQuery(filters({ from: '2026-09-01', to: '2026-10-01' }))).toEqual({
      since: '2026-09-01',
      until: '2026-10-01',
      limit: 10,
    })
    expect(toHistoryQuery(filters({ to: '2026-10-01' }))).toEqual({
      until: '2026-10-01',
      limit: 10,
    })
  })

  it('combines every criterion into one query', () => {
    expect(
      toHistoryQuery(
        filters({
          text: 'qwen',
          source: 'huggingface',
          topic: 'Model releases',
          from: '2026-09-01',
          to: '2026-10-01',
        }),
      ),
    ).toEqual({
      text: 'qwen',
      sources: 'huggingface',
      topics: 'Model releases',
      since: '2026-09-01',
      until: '2026-10-01',
      limit: 10,
    })
  })

  it('counts the filters that are set', () => {
    expect(filterCount(filters())).toBe(0)
    expect(filterCount(filters({ text: 'x' }))).toBe(1)
    expect(filterCount(filters({ source: 'all', text: ' x ', to: '2026-10-01' }))).toBe(2)
    expect(
      filterCount(
        filters({
          text: 'x',
          source: 'juya',
          topic: 'Headlines',
          from: '2026-09-01',
          to: '2026-10-01',
        }),
      ),
    ).toBe(5)
  })
})

describe('toHistoryResultVm', () => {
  const MATCH: HistorySearchMatchOut = {
    ref: { token: 'd15r9', digest_id: 15, run_id: 4, entry_id: 9, rank: 9 },
    generated_at: '2026-10-01T20:04:00',
    source_kind: 'juya',
    title: 'Moonshot ships Kimi K3',
    url: 'https://example.com/kimi-k3',
    excerpt: 'A longer context window.',
    score: 4,
    topics: ['Model releases'],
  }

  function result(overrides: Partial<HistorySearchResultOut> = {}): HistorySearchResultOut {
    return {
      matches: [MATCH],
      scanned_count: 42,
      archive_truncated: false,
      caveats: [],
      ...overrides,
    }
  }

  it('counts one result in the singular with no filter suffix', () => {
    const vm = toHistoryResultVm(result(), 0)

    expect(vm.countLabel).toBe('1 result')
    expect(vm.matches).toHaveLength(1)
    expect(vm.matches[0]?.token).toBe('d15r9')
  })

  it('reports several results and the filters behind them', () => {
    expect(
      toHistoryResultVm(result({ matches: [MATCH, MATCH, MATCH] }), 2).countLabel,
    ).toBe('3 results · 2 filters')
    expect(toHistoryResultVm(result({ matches: [] }), 1).countLabel).toBe('0 results · 1 filter')
  })

  it('numbers the filters in the singular when only one is set', () => {
    expect(toHistoryResultVm(result(), 1).countLabel).toBe('1 result · 1 filter')
  })

  it('passes the backend caveats through as notes and flags an empty list', () => {
    const vm = toHistoryResultVm(
      result({ matches: [], caveats: ['No saved digests to search.'] }),
      1,
    )

    expect(vm.notes).toEqual(['No saved digests to search.'])
    expect(vm.empty).toBe(true)
  })

  it('adds a truncation note when the backend sent none', () => {
    const vm = toHistoryResultVm(result({ archive_truncated: true }), 1)

    expect(vm.notes).toEqual([
      'The search scanned only the newest matching entries; older archive rows were not searched.',
    ])
  })

  it('keeps the backend truncation caveat instead of repeating it', () => {
    const caveat =
      'Search scanned the newest 42 matching entries; older archive rows were not searched.'
    const vm = toHistoryResultVm(result({ archive_truncated: true, caveats: [caveat] }), 1)

    expect(vm.notes).toEqual([caveat])
  })

  it('drops the backend no-match caveat because the empty state says it', () => {
    const vm = toHistoryResultVm(
      result({ matches: [], caveats: ["No historical digest entries matched text='zzz'."] }),
      1,
    )

    expect(vm.notes).toEqual([])
  })
})

describe('toOpenedVm', () => {
  function openedEntry(overrides: Partial<DigestEntryView> = {}): DigestEntryView {
    return {
      source_kind: 'zhihu',
      source_id: 'zhihu-9',
      title: 'Why small models are winning',
      source_name: 'Zhihu',
      source_url: 'https://www.zhihu.com/question/123',
      summary: 'A discussion of small model deployments.',
      why_it_matters: 'Cheaper inference changes what is worth building.',
      background_knowledge: 'Small models trade accuracy for cost.',
      follow_up_action: 'read',
      confidence_caveat: 'Single thread.',
      display_rank: 9,
      ...overrides,
    }
  }

  function show(overrides: Partial<HistoryItemShowOut> = {}): HistoryItemShowOut {
    return {
      token: 'd15r9',
      markdown: '# Moonshot ships Kimi K3\n\nA longer context window.',
      entry: openedEntry(),
      ...overrides,
    }
  }

  it('keeps the token and renders the entry through the shared mapper', () => {
    const vm = toOpenedVm(show())

    expect(vm.token).toBe('d15r9')
    expect(vm.entry).toMatchObject({
      kind: 'zhihu',
      rank: 9,
      title: 'Why small models are winning',
      host: 'zhihu.com',
      followUp: 'read',
    })
    expect(vm.markdown).toBe('# Moonshot ships Kimi K3\n\nA longer context window.')
  })

  it('falls back to the markdown when the entry is null', () => {
    const vm = toOpenedVm(show({ entry: null }))

    expect(vm.entry).toBeNull()
    expect(vm.markdown).toBe('# Moonshot ships Kimi K3\n\nA longer context window.')
  })

  it('falls back to the markdown when the entry is missing', () => {
    const vm = toOpenedVm({ token: 'd12r1', markdown: 'Body only.' })

    expect(vm.entry).toBeNull()
    expect(vm.markdown).toBe('Body only.')
  })
})
