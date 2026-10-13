import { describe, expect, it } from 'vitest'

import type { MessageOut, RequestOut, SessionOut } from '@/api/generated/types.gen'
import { createRequestLifecycle, type LifecycleDeps } from '@/api/lifecycle'
import type { SseEvent } from '@/api/sse'
import { createThreadController, type ThreadDeps } from '@/stores/thread'
import { toMessageVm } from '@/vm/session'

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

/** Resolve once `predicate` holds, so tests never depend on a fixed number of ticks. */
async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (predicate()) {
      return
    }
    await new Promise((resolve) => {
      setTimeout(resolve, 0)
    })
  }
  throw new Error('condition was never reached')
}

function message(overrides: Partial<MessageOut> = {}): MessageOut {
  return {
    id: 1,
    session_id: 's1',
    sequence: 1,
    role: 'user',
    content: 'What shipped this week?',
    run_id: null,
    created_at: '2026-10-01T20:04:00Z',
    digest_id: null,
    warnings: [],
    digest: null,
    ...overrides,
  }
}

function sessionOut(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: 's1',
    title: 'Open models & agent tools',
    connector_names: ['juya', 'github'],
    items_per_source: 5,
    created_at: '2026-10-01T20:00:00Z',
    updated_at: '2026-10-01T20:04:00Z',
    digest_count: 1,
    active_request_id: null,
    ...overrides,
  }
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
    started_at: '2026-10-01T20:14:00Z',
    completed_at: null,
    ...overrides,
  }
}

const started: SseEvent = { event: 'started', data: { request_id: 'r1', user_message_id: 1 } }

function progress(
  stage: string,
  source: string,
  status: 'running' | 'done' | 'failed',
  count: number | null = null,
): SseEvent {
  return { event: 'progress', data: { stage, source, status, count } }
}

/** Local clock label for a fixed time of day, so stamped labels are predictable. */
function at(hour: number, minute: number, second: number): Date {
  return new Date(2026, 9, 1, hour, minute, second)
}

interface StoreOptions {
  post?: LifecycleDeps['post']
  getRequest?: LifecycleDeps['getRequest']
  loadMessages?: ThreadDeps['loadMessages']
  schedule?: ThreadDeps['schedule']
  now?: () => Date
}

function makeStore(options: StoreOptions = {}) {
  const reloads: string[] = []
  const lifecycle = createRequestLifecycle({
    post: options.post ?? (async () => events([])),
    getRequest: options.getRequest ?? (async () => requestOut()),
    cancel: async () => 202,
    reloadMessages: async (sessionId) => {
      reloads.push(sessionId)
    },
    sleep: async () => undefined,
    backoffMs: [1],
  })
  const controller = createThreadController({
    loadMessages: options.loadMessages ?? (async () => []),
    lifecycle,
    now: options.now ?? (() => at(20, 14, 1)),
    schedule: options.schedule ?? (() => undefined),
  })
  return { controller, lifecycle, reloads }
}

describe('thread store session loading', () => {
  it('renders a loaded page in reading order and resumes an active request', async () => {
    const store = makeStore({
      loadMessages: async () => [
        message({ id: 3, sequence: 3, role: 'assistant', content: 'Third' }),
        message({ id: 1, sequence: 1, content: 'First' }),
        message({ id: 2, sequence: 2, role: 'assistant', content: 'Second' }),
      ],
      getRequest: async () => requestOut({ status: 'succeeded' }),
    })

    await store.controller.openSession(sessionOut({ active_request_id: 'r1' }))

    expect(store.controller.messages.value.map((item) => item.text)).toEqual([
      'First',
      'Second',
      'Third',
    ])
    expect(store.reloads).toEqual(['s1'])
    expect(store.controller.snapshot.value.state).toBe('succeeded')
    // The reconnected dwell keeps the card up for one beat before the reload lands.
    expect(store.controller.run.value?.reconnect?.ok).toBe(true)
  })

  it('makes no request for a conversation that is not open', async () => {
    let loads = 0
    const store = makeStore({
      loadMessages: async () => {
        loads += 1
        return []
      },
    })

    await store.controller.openSession(null)

    expect(loads).toBe(0)
    expect(store.controller.snapshot.value.state).toBe('idle')
  })
})

describe('thread store live run clocks', () => {
  it('stamps the run start and each finished source from the local clock', async () => {
    const hold = deferred()
    const store = makeStore({
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Calling github…', 'github', 'running')
          yield progress('Done github: Found 3 github results.', 'github', 'done', 3)
          await hold.promise
        })(),
    })

    await store.controller.openSession(sessionOut())
    const sending = store.lifecycle.send('s1', { content: 'what is new?' })
    await waitFor(() => store.controller.run.value !== null)

    const run = store.controller.run.value
    expect(run?.startedAt).toBe('20:14:01')
    expect(run?.steps.find((step) => step.source === 'github')).toMatchObject({
      status: 'done',
      count: 3,
      at: '20:14:01',
    })
    expect(run?.steps.find((step) => step.source === 'juya')?.at).toBeNull()

    hold.resolve()
    await sending
  })

  it('starts a new request with a fresh start clock', async () => {
    const firstHold = deferred()
    const secondHold = deferred()
    let current = at(20, 14, 1)
    let calls = 0
    const store = makeStore({
      now: () => current,
      post: async () => {
        calls += 1
        const hold = calls === 1 ? firstHold : secondHold
        return (async function* generate() {
          yield started
          yield progress('Calling github…', 'github', 'running')
          await hold.promise
        })()
      },
    })

    const first = store.lifecycle.send('s1', { content: 'first' })
    await waitFor(() => store.controller.run.value?.startedAt === '20:14:01')

    firstHold.resolve()
    await first

    current = at(20, 15, 30)
    const second = store.lifecycle.send('s1', { content: 'second' })
    await waitFor(() => store.controller.run.value?.startedAt === '20:15:30')

    expect(store.controller.run.value?.startedAt).toBe('20:15:30')
    secondHold.resolve()
    await second
  })

  it('reports a cancelled run with the clock it ended', async () => {
    let current = at(20, 14, 1)
    const store = makeStore({
      now: () => current,
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Calling github…', 'github', 'running')
          current = at(20, 14, 7)
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
    })

    await store.controller.openSession(sessionOut())
    await store.lifecycle.send('s1', { content: 'what is new?' })

    expect(store.controller.cancelled.value).toEqual({
      mode: 'digest',
      at: '20:14:07',
      done: 0,
      total: 2,
    })
    expect(store.controller.run.value).toBeNull()
    expect(store.controller.alert.value).toBeNull()
  })

  it('surfaces a failed run as the safe alert with Run again', async () => {
    const store = makeStore({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'workflow_error',
              message: 'Something went wrong.',
              correlation_id: 'c1',
            },
          },
        ]),
    })

    await store.lifecycle.send('s1', { content: 'what is new?' })

    expect(store.controller.alert.value).toEqual({
      kind: 'failed',
      message: 'Something went wrong.',
      canRunAgain: true,
    })
    expect(store.controller.run.value).toBeNull()
  })
})

describe('thread store transcript refresh', () => {
  it('reloads the transcript when the run reaches an outcome', async () => {
    let loads = 0
    const store = makeStore({
      loadMessages: async () => {
        loads += 1
        return [
          message({
            id: loads === 1 ? 1 : 4,
            sequence: loads === 1 ? 1 : 4,
            role: 'assistant',
            content: loads === 1 ? 'Before the digest' : 'Digest is here',
          }),
        ]
      },
      post: async () =>
        events([
          started,
          progress('Calling github…', 'github', 'running'),
          { event: 'done', data: { request_id: 'r1', message_id: 4, run_id: 9, path: 'digest' } },
        ]),
    })

    await store.controller.openSession(sessionOut())
    expect(store.controller.messages.value.map((item) => item.text)).toEqual(['Before the digest'])

    await store.lifecycle.send('s1', { content: 'digest please' })

    expect(store.controller.messages.value.map((item) => item.text)).toEqual(['Digest is here'])
    expect(store.controller.run.value).toBeNull()
  })

  it('does not repeat a cancelled reply that the transcript also carries', async () => {
    const store = makeStore({
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

    await store.controller.openSession(sessionOut())
    await store.lifecycle.send('s1', { content: 'digest please' })
    expect(store.controller.cancelled.value).not.toBeNull()

    // The reload lands with the terminal assistant row the backend persisted.
    store.controller.messages.value = [
      toMessageVm(
        message({ id: 1, sequence: 1, role: 'assistant', content: 'The request was cancelled.' }),
      ),
    ]

    expect(store.controller.visibleMessages.value).toEqual([])
    expect(store.controller.cancelled.value).not.toBeNull()
  })

  it('does not repeat the failed message that the transcript also carries', async () => {
    const store = makeStore({
      post: async () =>
        events([
          started,
          {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'workflow_error',
              message: 'Digest generation failed.',
              correlation_id: 'c1',
            },
          },
        ]),
    })

    await store.controller.openSession(sessionOut())
    await store.lifecycle.send('s1', { content: 'digest please' })
    expect(store.controller.alert.value?.message).toBe('Digest generation failed.')

    store.controller.messages.value = [
      toMessageVm(
        message({ id: 2, sequence: 2, role: 'assistant', content: 'Digest generation failed.' }),
      ),
    ]

    expect(store.controller.visibleMessages.value).toEqual([])
    expect(store.controller.alert.value).not.toBeNull()
  })
})

describe('thread store run again', () => {
  it('refills the draft from the last user message without sending', async () => {
    const store = makeStore({
      loadMessages: async () => [
        message({ id: 1, sequence: 1, content: 'What shipped this week?' }),
        message({ id: 2, sequence: 2, role: 'assistant', content: 'A digest.' }),
      ],
    })

    await store.controller.openSession(sessionOut())
    store.controller.runAgain()

    expect(store.controller.draft.value).toBe('What shipped this week?')
    expect(store.controller.run.value).toBeNull()
  })
})
