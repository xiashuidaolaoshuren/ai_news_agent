import { describe, expect, it } from 'vitest'

import type {
  HistoryItemShowOut,
  HistorySearchMatchOut,
  HistorySearchResultOut,
} from '@/api/generated/types.gen'
import {
  createHistoryController,
  type HistoryDeps,
} from '@/stores/history'
import type { HistorySearchQuery } from '@/vm'

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

function resultOut(overrides: Partial<HistorySearchResultOut> = {}): HistorySearchResultOut {
  return {
    matches: [MATCH],
    scanned_count: 42,
    archive_truncated: false,
    caveats: [],
    ...overrides,
  }
}

function showOut(overrides: Partial<HistoryItemShowOut> = {}): HistoryItemShowOut {
  return {
    token: 'd15r9',
    markdown: '# Moonshot ships Kimi K3',
    entry: {
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
    },
    ...overrides,
  }
}

interface Timer {
  handler: () => void
  ms: number
  cancelled: boolean
}

interface Harness {
  deps: HistoryDeps
  searches: HistorySearchQuery[]
  shows: string[]
  askedTitles: string[]
  timers: Timer[]
  /** Run the scheduled work that is still pending, then settle its promises. */
  flush(): Promise<void>
  /** Let an already started request finish. */
  settle(): Promise<void>
}

interface HarnessOptions {
  search?(query: HistorySearchQuery): Promise<HistorySearchResultOut>
  show?(token: string): Promise<HistoryItemShowOut>
}

function makeHistory(options: HarnessOptions = {}): Harness {
  const searches: HistorySearchQuery[] = []
  const shows: string[] = []
  const askedTitles: string[] = []
  const timers: Timer[] = []

  const deps: HistoryDeps = {
    async search(query): Promise<HistorySearchResultOut> {
      searches.push(query)
      return options.search === undefined ? resultOut() : options.search(query)
    },
    async show(token): Promise<HistoryItemShowOut> {
      shows.push(token)
      return options.show === undefined ? showOut({ token }) : options.show(token)
    },
    prefillFollowUp: (title) => {
      askedTitles.push(title)
    },
    schedule: (handler, ms) => {
      const timer: Timer = { handler, ms, cancelled: false }
      timers.push(timer)
      return timer
    },
    cancel: (handle) => {
      const timer = handle as Timer
      timer.cancelled = true
    },
  }

  async function settle(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, 0))
  }

  async function flush(): Promise<void> {
    for (const timer of timers.splice(0)) {
      if (!timer.cancelled) {
        timer.handler()
      }
    }
    await settle()
  }

  return { deps, searches, shows, askedTitles, timers, flush, settle }
}

describe('history search', () => {
  it('collapses keystrokes into one debounced request with the mapped query', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'gguf' })
    controller.setFilters({ text: 'gguf quant' })

    expect(harness.searches).toEqual([])
    expect(harness.timers).toHaveLength(2)
    expect(harness.timers[0]?.cancelled).toBe(true)
    expect(harness.timers[1]?.ms).toBe(250)

    await harness.flush()

    expect(harness.searches).toEqual([{ text: 'gguf quant', limit: 10 }])
  })

  it('fills the results and the count line from the response', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'qwen', source: 'hf' })
    expect(controller.vm.value.state).toBe('loading')

    await harness.flush()

    expect(harness.searches).toEqual([{ text: 'qwen', sources: 'huggingface', limit: 10 }])
    expect(controller.vm.value.state).toBe('results')
    expect(controller.vm.value.countLabel).toBe('1 result · 2 filters')
    expect(controller.vm.value.matches.map((match) => match.token)).toEqual(['d15r9'])
    expect(controller.vm.value.matches[0]?.label).toBe('Juya')
  })

  it('drops a response that arrives after the filters moved on', async () => {
    const pending: ((out: HistorySearchResultOut) => void)[] = []
    const harness = makeHistory({
      search: () =>
        new Promise<HistorySearchResultOut>((resolve) => {
          pending.push(resolve)
        }),
    })
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'first' })
    await harness.flush()
    controller.setFilters({ text: 'second' })
    await harness.flush()

    expect(harness.searches).toEqual([
      { text: 'first', limit: 10 },
      { text: 'second', limit: 10 },
    ])

    pending[1]?.(resultOut({ matches: [MATCH, MATCH] }))
    await harness.settle()
    expect(controller.vm.value.matches).toHaveLength(2)

    pending[0]?.(resultOut({ matches: [] }))
    await harness.settle()

    expect(controller.vm.value.state).toBe('results')
    expect(controller.vm.value.matches).toHaveLength(2)
  })

  it('returns to idle and drops the results when the last filter is cleared', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'gguf' })
    await harness.flush()
    expect(controller.vm.value.state).toBe('results')

    controller.setFilters({ text: '   ' })
    await harness.flush()

    expect(harness.searches).toHaveLength(1)
    expect(controller.vm.value.state).toBe('idle')
    expect(controller.vm.value.matches).toEqual([])
    expect(controller.vm.value.countLabel).toBe('')
    expect(controller.vm.value.notes).toEqual([])
  })
})

describe('history states', () => {
  it('reports no matches with the copy, the filters behind it, and a clear action', async () => {
    const harness = makeHistory({ search: async () => resultOut({ matches: [] }) })
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'zzz' })
    await harness.flush()

    expect(controller.vm.value.state).toBe('empty')
    expect(controller.vm.value.emptyTitle).toBe('No matches')
    expect(controller.vm.value.emptyBody).toBe(
      'Nothing in past digests matches “zzz”. Try a broader term or remove a filter.',
    )
    expect(controller.vm.value.countLabel).toBe('0 results · 1 filter')
  })

  it('names the source, the topic, and the dates in the no-match copy', async () => {
    const harness = makeHistory({ search: async () => resultOut({ matches: [] }) })
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ source: 'juya', topic: 'Headlines' })
    await harness.flush()
    expect(controller.vm.value.emptyBody).toBe(
      'Nothing in past digests matches from Juya in Headlines. Try a broader term or remove a filter.',
    )

    controller.setFilters({ source: 'all', topic: '', from: '2026-09-01' })
    await harness.flush()
    expect(controller.vm.value.emptyBody).toBe(
      'Nothing in past digests matches in the selected date range. Try a broader term or remove a filter.',
    )
  })

  it('clears every filter back to the idle prompt', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'qwen', source: 'hf' })
    await harness.flush()
    expect(controller.vm.value.state).toBe('results')

    controller.clearFilters()

    expect(controller.vm.value.filters).toEqual({
      text: '',
      source: 'all',
      topic: '',
      from: '',
      to: '',
    })
    expect(controller.vm.value.state).toBe('idle')
    expect(controller.vm.value.emptyTitle).toBe('Search past digests')
  })

  it('shows the failure inline and recovers when the search is retried', async () => {
    let failing = true
    const harness = makeHistory({
      search: async () => {
        if (failing) {
          throw new Error("Unknown source 'typo'; allowed: github, juya, zhihu")
        }
        return resultOut()
      },
    })
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'qwen' })
    await harness.flush()

    expect(controller.vm.value.state).toBe('error')
    expect(controller.vm.value.error).toBe(
      "Unknown source 'typo'; allowed: github, juya, zhihu",
    )
    expect(controller.vm.value.matches).toEqual([])

    failing = false
    controller.retry()
    await harness.settle()

    expect(harness.searches).toHaveLength(2)
    expect(controller.vm.value.state).toBe('results')
    expect(controller.vm.value.error).toBeNull()
    expect(controller.vm.value.matches).toHaveLength(1)
  })

  it('uses its own copy when the failure is not an Error', async () => {
    const harness = makeHistory({
      search: async () => {
        throw 'offline'
      },
    })
    const controller = createHistoryController(harness.deps)

    controller.setFilters({ text: 'qwen' })
    await harness.flush()

    expect(controller.vm.value.state).toBe('error')
    expect(controller.vm.value.error).toBe('History search failed. Try again.')
  })
})

describe('history opened result', () => {
  async function opened() {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)
    controller.setFilters({ text: 'qwen' })
    await harness.flush()
    return { harness, controller, match: controller.vm.value.matches[0]! }
  }

  it('fetches the historical item and renders its entry without touching the filters', async () => {
    const { harness, controller, match } = await opened()

    expect(controller.vm.value.opened).toBeNull()

    controller.open(match)
    expect(controller.vm.value.opened?.loading).toBe(true)
    expect(controller.vm.value.opened?.match.token).toBe('d15r9')

    await harness.settle()

    expect(harness.shows).toEqual(['d15r9'])
    expect(controller.vm.value.opened?.loading).toBe(false)
    expect(controller.vm.value.opened?.error).toBeNull()
    expect(controller.vm.value.opened?.item?.entry).toMatchObject({
      kind: 'zhihu',
      rank: 9,
      title: 'Why small models are winning',
    })
    // Opening is read-only: the results and the filters stay as they were.
    expect(controller.vm.value.state).toBe('results')
    expect(controller.vm.value.matches).toHaveLength(1)
    expect(harness.searches).toHaveLength(1)
  })

  it('reports a failed open inline and keeps the results', async () => {
    const harness = makeHistory({
      show: async () => {
        throw new Error('historical item not found')
      },
    })
    const controller = createHistoryController(harness.deps)
    controller.setFilters({ text: 'qwen' })
    await harness.flush()

    controller.open(controller.vm.value.matches[0]!)
    await harness.settle()

    expect(controller.vm.value.opened?.loading).toBe(false)
    expect(controller.vm.value.opened?.error).toBe('historical item not found')
    expect(controller.vm.value.opened?.item).toBeNull()
    expect(controller.vm.value.state).toBe('results')
  })

  it('uses its own copy when the open failure is not an Error', async () => {
    const harness = makeHistory({
      show: async () => {
        throw { status: 404 }
      },
    })
    const controller = createHistoryController(harness.deps)
    controller.setFilters({ text: 'qwen' })
    await harness.flush()

    controller.open(controller.vm.value.matches[0]!)
    await harness.settle()

    expect(controller.vm.value.opened?.error).toBe('Could not open this result.')
  })

  it('closes the opened result and leaves the list alone', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)
    controller.setFilters({ text: 'qwen' })
    await harness.flush()
    controller.open(controller.vm.value.matches[0]!)
    await harness.settle()

    controller.closeResult()

    expect(controller.vm.value.opened).toBeNull()
    expect(controller.vm.value.state).toBe('results')
    expect(controller.vm.value.matches).toHaveLength(1)
  })

  it('asks in chat about the entry the user opened', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)
    controller.setFilters({ text: 'qwen' })
    await harness.flush()
    controller.open(controller.vm.value.matches[0]!)
    await harness.settle()

    controller.askInChat('Why small models are winning')

    expect(harness.askedTitles).toEqual(['Why small models are winning'])
  })

  it('closes the opened result when the filters are cleared', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)
    controller.setFilters({ text: 'qwen' })
    await harness.flush()
    controller.open(controller.vm.value.matches[0]!)
    await harness.settle()
    expect(controller.vm.value.opened).not.toBeNull()

    controller.clearFilters()

    expect(controller.vm.value.opened).toBeNull()
    expect(controller.vm.value.state).toBe('idle')
    expect(controller.vm.value.matches).toEqual([])
  })
})

describe('history idle state', () => {
  it('makes no request and shows the idle prompt until a filter is set', async () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)

    expect(controller.vm.value.state).toBe('idle')
    expect(controller.vm.value.emptyTitle).toBe('Search past digests')
    expect(controller.vm.value.emptyBody).toBe(
      'Enter text, a source, a topic or a date range.',
    )

    await harness.flush()

    expect(harness.searches).toEqual([])
    expect(controller.vm.value.countLabel).toBe('')
    expect(controller.vm.value.matches).toEqual([])
    expect(controller.vm.value.notes).toEqual([])
  })

  it('names every source kind and starts on all sources', () => {
    const harness = makeHistory()
    const controller = createHistoryController(harness.deps)

    expect(controller.vm.value.filters.source).toBe('all')
    expect(controller.vm.value.sourceOptions.map((option) => option.value)).toEqual([
      'all',
      'juya',
      'huggingface',
      'github',
      'zhihu',
      'bilibili',
    ])
  })
})
