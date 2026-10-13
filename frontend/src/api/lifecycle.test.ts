import { describe, expect, it } from 'vitest'

import type { RequestOut } from '@/api/generated/types.gen'
import {
  createRequestLifecycle,
  type LifecycleDeps,
  type RequestLifecycle,
  type RequestSnapshot,
} from '@/api/lifecycle'
import type { SseEvent } from '@/api/sse'
import { SseHttpError } from '@/api/sse'

function deferred<T = void>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function events(list: SseEvent[]): AsyncIterable<SseEvent> {
  return (async function* generate() {
    for (const event of list) {
      yield event
    }
  })()
}

/** Resolve once the lifecycle snapshot satisfies `predicate`. */
function when(
  lifecycle: RequestLifecycle,
  predicate: (snapshot: RequestSnapshot) => boolean,
): Promise<void> {
  return new Promise((resolve) => {
    if (predicate(lifecycle.state)) {
      resolve()
      return
    }
    const off = lifecycle.subscribe((snapshot) => {
      if (predicate(snapshot)) {
        off()
        resolve()
      }
    })
  })
}

function requestOut(overrides: Partial<RequestOut> = {}): RequestOut {
  return {
    id: 'r1',
    session_id: 's1',
    status: 'active',
    user_message_id: 1,
    assistant_message_id: null,
    run_id: null,
    error_code: null,
    error_message: null,
    started_at: '2026-10-11T00:00:00Z',
    completed_at: null,
    ...overrides,
  }
}

function makeLifecycle(overrides: Partial<LifecycleDeps> = {}) {
  const deps: LifecycleDeps = {
    post: async () => events([]),
    getRequest: async () => requestOut(),
    cancel: async () => 202,
    reloadMessages: async () => undefined,
    sleep: async () => undefined,
    ...overrides,
  }
  return createRequestLifecycle(deps)
}

const started: SseEvent = {
  event: 'started',
  data: { request_id: 'r1', user_message_id: 1 },
}

/** Digest event with a minimal `DigestView`; override ids per test. */
function digestEvent(
  overrides: Partial<{ run_id: number; digest_id: number; markdown: string }> = {},
): Extract<SseEvent, { event: 'digest' }> {
  return {
    event: 'digest',
    data: {
      run_id: overrides.run_id ?? 4,
      digest_id: overrides.digest_id ?? 12,
      digest: { generated_at: '2026-10-11T00:00:00Z', entries: [] },
      markdown: overrides.markdown ?? '# digest',
      warnings: [],
      errors: [],
    },
  }
}

describe('createRequestLifecycle streaming', () => {
  it('tracks requestId, appends progress, and replaces cumulative delta text', async () => {
    const hold = deferred()
    const lifecycle = makeLifecycle({
      post: async (sessionId, body) => {
        expect(sessionId).toBe('s1')
        expect(body.content).toBe('hi')
        return (async function* generate() {
          yield started
          yield {
            event: 'progress',
            data: { stage: 'Calling github…', source: 'github', status: 'running' },
          } satisfies SseEvent
          yield {
            event: 'progress',
            data: { stage: 'Done github: Found 3 github result(s).', source: 'github', status: 'done', count: 3 },
          } satisfies SseEvent
          yield { event: 'delta', data: { text: 'a' } } satisfies SseEvent
          yield { event: 'delta', data: { text: 'ab' } } satisfies SseEvent
          await hold.promise
        })()
      },
    })

    const run = lifecycle.send('s1', { content: 'hi' })
    await when(lifecycle, (snapshot) => snapshot.text === 'ab')

    expect(lifecycle.state.state).toBe('streaming')
    expect(lifecycle.state.requestId).toBe('r1')
    expect(lifecycle.state.progress).toEqual([
      { stage: 'Calling github…', source: 'github', status: 'running' },
      {
        stage: 'Done github: Found 3 github result(s).',
        source: 'github',
        status: 'done',
        count: 3,
      },
    ])
    expect(lifecycle.state.text).toBe('ab')

    hold.resolve()
    await run
  })

  it('becomes succeeded with the digest after digest and done', async () => {
    const digest = digestEvent({
      run_id: 4,
      digest_id: 12,
      markdown: '# digest',
    })
    const lifecycle = makeLifecycle({
      post: async () =>
        events([
          started,
          digest,
          {
            event: 'done',
            data: { request_id: 'r1', message_id: 9, run_id: 4, path: 'digest' },
          },
        ]),
    })

    await lifecycle.send('s1', { content: 'hi' })

    expect(lifecycle.state.state).toBe('succeeded')
    expect(lifecycle.state.requestId).toBe('r1')
    expect(lifecycle.state.digest).toEqual(digest.data)
  })

  it('maps a terminal error to cancelled or failed', async () => {
    const cancelRun = makeLifecycle({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'cancelled',
              message: 'The request was cancelled.',
              correlation_id: 'c1',
            },
          },
        ]),
    })
    await cancelRun.send('s1', { content: 'hi' })
    expect(cancelRun.state.state).toBe('cancelled')
    expect(cancelRun.state.error?.code).toBe('cancelled')

    const failRun = makeLifecycle({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'workflow_error',
              message: 'Something went wrong.',
              correlation_id: 'c2',
            },
          },
        ]),
    })
    await failRun.send('s1', { content: 'hi' })
    expect(failRun.state.state).toBe('failed')
    expect(failRun.state.error?.code).toBe('workflow_error')
    expect(failRun.state.error?.message).toBe('Something went wrong.')
  })

  it('stays streaming after a 202 cancel until the terminal cancelled error arrives', async () => {
    const hold = deferred()
    const cancelCalls: Array<[string, string]> = []
    const lifecycle = makeLifecycle({
      post: async () =>
        (async function* generate() {
          yield started
          await hold.promise
          yield {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'cancelled',
              message: 'The request was cancelled.',
              correlation_id: 'c1',
            },
          } satisfies SseEvent
        })(),
      cancel: async (sessionId, requestId) => {
        cancelCalls.push([sessionId, requestId])
        return 202
      },
    })

    const run = lifecycle.send('s1', { content: 'hi' })
    await when(lifecycle, (snapshot) => snapshot.requestId === 'r1')

    const cancelling = lifecycle.cancel()
    expect(cancelCalls).toEqual([['s1', 'r1']])
    await Promise.resolve()
    expect(lifecycle.state.state).toBe('streaming')

    hold.resolve()
    await cancelling
    await run

    expect(lifecycle.state.state).toBe('cancelled')
    expect(lifecycle.state.error?.code).toBe('cancelled')
  })

  it('polls once after a 204 cancel and shows the real outcome', async () => {
    const hold = deferred()
    const reloads: string[] = []
    let polls = 0
    const lifecycle = makeLifecycle({
      post: async () =>
        (async function* generate() {
          yield started
          await hold.promise
        })(),
      cancel: async () => 204,
      getRequest: async () => {
        polls += 1
        return requestOut({ status: 'succeeded', assistant_message_id: 9 })
      },
      reloadMessages: async (sessionId) => {
        reloads.push(sessionId)
      },
    })

    const run = lifecycle.send('s1', { content: 'hi' })
    await when(lifecycle, (snapshot) => snapshot.requestId === 'r1')

    await lifecycle.cancel()

    expect(polls).toBe(1)
    expect(lifecycle.state.state).toBe('succeeded')
    expect(reloads).toEqual(['s1'])

    hold.resolve()
    await run
  })
})

describe('createRequestLifecycle terminal status', () => {
  it('records a polled interruption so it is distinguishable from a failure', async () => {
    const lifecycle = makeLifecycle({
      backoffMs: [10],
      post: async () => events([started]),
      getRequest: async () => requestOut({ status: 'interrupted' }),
    })

    await lifecycle.resume('s1', 'r1')

    expect(lifecycle.state.state).toBe('failed')
    expect(lifecycle.state.terminalStatus).toBe('interrupted')
  })

  it('records the outcome a terminal error event carries', async () => {
    const cancelRun = makeLifecycle({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'cancelled',
              message: 'The request was cancelled.',
              correlation_id: 'c1',
            },
          },
        ]),
    })
    await cancelRun.send('s1', { content: 'hi' })
    expect(cancelRun.state.terminalStatus).toBe('cancelled')

    const failRun = makeLifecycle({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'workflow_error',
              message: 'Something went wrong.',
              correlation_id: 'c2',
            },
          },
        ]),
    })
    await failRun.send('s1', { content: 'hi' })
    expect(failRun.state.terminalStatus).toBe('failed')

    const interruptedRun = makeLifecycle({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'interrupted',
              message: 'This request was interrupted by a restart',
              correlation_id: 'c3',
            },
          },
        ]),
    })
    await interruptedRun.send('s1', { content: 'hi' })
    expect(interruptedRun.state.state).toBe('failed')
    expect(interruptedRun.state.terminalStatus).toBe('interrupted')
  })

  it('records a succeeded outcome when done arrives without a digest', async () => {
    const lifecycle = makeLifecycle({
      post: async () =>
        events([
          started,
          { event: 'delta', data: { text: 'A GGUF file is quantized.' } },
          {
            event: 'done',
            data: { request_id: 'r1', message_id: 9, run_id: null, path: 'followup' },
          },
        ]),
    })

    await lifecycle.send('s1', { content: 'hi' })

    expect(lifecycle.state.state).toBe('succeeded')
    expect(lifecycle.state.terminalStatus).toBe('succeeded')
  })
})

describe('createRequestLifecycle reconnect', () => {
  it('reconnects with backoff after a dropped stream and never reopens the stream', async () => {
    const sleeps: number[] = []
    const reloads: string[] = []
    const reconnecting: Array<{ attempt: number; nextDelayMs: number | null }> = []
    let posts = 0
    let polls = 0
    const statuses = ['active', 'active', 'succeeded']

    const lifecycle = makeLifecycle({
      backoffMs: [10, 20, 30, 40, 50],
      post: async () => {
        posts += 1
        return events([started, { event: 'delta', data: { text: 'hello' } }])
      },
      getRequest: async () => requestOut({ status: statuses[polls++] ?? 'succeeded' }),
      sleep: async (ms) => {
        sleeps.push(ms)
      },
      reloadMessages: async (sessionId) => {
        reloads.push(sessionId)
      },
    })
    lifecycle.subscribe((snapshot) => {
      if (snapshot.state === 'reconnecting') {
        reconnecting.push({ attempt: snapshot.attempt, nextDelayMs: snapshot.nextDelayMs })
      }
    })

    await lifecycle.send('s1', { content: 'hi' })

    expect(posts).toBe(1)
    expect(sleeps).toEqual([10, 20, 30])
    expect(reconnecting).toEqual([
      { attempt: 1, nextDelayMs: 10 },
      { attempt: 2, nextDelayMs: 20 },
      { attempt: 3, nextDelayMs: 30 },
    ])
    expect(lifecycle.state.state).toBe('succeeded')
    expect(lifecycle.state.text).toBe('hello')
    expect(reloads).toEqual(['s1'])
  })

  it('fails after five active polls and lets resume poll again', async () => {
    const sleeps: number[] = []
    const reloads: string[] = []
    let polls = 0
    const lifecycle = makeLifecycle({
      backoffMs: [10, 20, 30, 40, 50],
      getRequest: async () => {
        polls += 1
        return requestOut({ status: polls <= 5 ? 'active' : 'cancelled' })
      },
      sleep: async (ms) => {
        sleeps.push(ms)
      },
      reloadMessages: async (sessionId) => {
        reloads.push(sessionId)
      },
    })

    await lifecycle.resume('s1', 'r1')

    expect(lifecycle.state.state).toBe('failed')
    expect(lifecycle.state.requestId).toBe('r1')
    expect(lifecycle.state.attempt).toBe(5)
    expect(lifecycle.state.nextDelayMs).toBeNull()
    expect(polls).toBe(5)
    expect(sleeps).toEqual([10, 20, 30, 40, 50])
    expect(reloads).toEqual([])

    await lifecycle.resume('s1', 'r1')

    expect(lifecycle.state.state).toBe('cancelled')
    expect(polls).toBe(6)
    expect(sleeps).toEqual([10, 20, 30, 40, 50, 10])
    expect(reloads).toEqual(['s1'])
  })
})

describe('createRequestLifecycle blocked sends', () => {
  it('surfaces a 409 detail code as blocked without opening a stream', async () => {
    for (const code of ['session_busy', 'request_in_progress'] as const) {
      let posted = 0
      const lifecycle = makeLifecycle({
        post: async () => {
          posted += 1
          throw new SseHttpError(409, code, 'request blocked')
        },
      })

      await lifecycle.send('s1', { content: 'hi' })

      expect(posted).toBe(1)
      expect(lifecycle.state.state).toBe('idle')
      expect(lifecycle.state.blocked).toBe(code)
    }
  })

  it('ignores events from a superseded stream', async () => {
    const firstHold = deferred()
    const secondHold = deferred()
    const lifecycle = makeLifecycle({
      post: async (_sessionId, body) =>
        body.content === 'first'
          ? (async function* generate() {
              yield started
              await firstHold.promise
              yield { event: 'delta', data: { text: 'stale' } } satisfies SseEvent
            })()
          : (async function* generate() {
              yield {
                event: 'started',
                data: { request_id: 'r2', user_message_id: 2 },
              } satisfies SseEvent
              await secondHold.promise
            })(),
    })

    const first = lifecycle.send('s1', { content: 'first' })
    await when(lifecycle, (snapshot) => snapshot.requestId === 'r1')

    const second = lifecycle.send('s1', { content: 'second' })
    await when(lifecycle, (snapshot) => snapshot.requestId === 'r2')

    firstHold.resolve()
    await first

    expect(lifecycle.state.text).toBe('')
    expect(lifecycle.state.requestId).toBe('r2')
    expect(lifecycle.state.state).toBe('streaming')

    secondHold.resolve()
    await second
  })
})
