import { describe, expect, it, vi } from 'vitest'

import type { MessageOut, RequestOut, SessionOut } from '@/api/generated/types.gen'
import { createRequestLifecycle, type LifecycleDeps } from '@/api/lifecycle'
import type { SseEvent } from '@/api/sse'
import { createThreadController, PENDING_MESSAGE_ID, type MessagePage, type ThreadDeps } from '@/stores/thread'
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
  loadMessages?: (
    sessionId: string,
    cursor?: string | null,
  ) => Promise<MessageOut[] | MessagePage>
  schedule?: ThreadDeps['schedule']
  now?: () => Date
  onSessionChanged?: ThreadDeps['onSessionChanged']
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
    // Most tests stub one page of rows; a page object carries a cursor as well. The
    // stub is called with the cursor only when the store asked for one.
    loadMessages: async (sessionId, cursor) => {
      const load = options.loadMessages ?? (async () => [])
      const page = await (cursor === undefined ? load(sessionId) : load(sessionId, cursor))
      return Array.isArray(page) ? { messages: page, nextCursor: null } : page
    },
    lifecycle,
    now: options.now ?? (() => at(20, 14, 1)),
    schedule: options.schedule ?? (() => undefined),
    onSessionChanged: options.onSessionChanged,
  })
  return { controller, lifecycle, reloads }
}

/** The sources a send carries, as the composer passes them to the thread. */
const SENT_SOURCES = { names: ['juya', 'github'], perSource: 5 }

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

describe('thread store pending user message', () => {
  it('shows the message just sent until the reloaded transcript carries it', async () => {
    const hold = deferred()
    const store = makeStore({
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Calling juya…', 'juya', 'running')
          await hold.promise
        })(),
    })
    await store.controller.openSession(sessionOut())

    store.controller.markUserSent('What shipped this week?', SENT_SOURCES)
    const sending = store.lifecycle.send('s1', { content: 'What shipped this week?' })
    await waitFor(() => store.controller.run.value !== null)

    expect(store.controller.visibleMessages.value.map((item) => item.text)).toEqual([
      'What shipped this week?',
    ])
    expect(store.controller.visibleMessages.value[0]?.kind).toBe('user')

    hold.resolve()
    await sending

    expect(store.controller.visibleMessages.value).toEqual([])
  })

  it('drops the pending message when another conversation is opened', async () => {
    const store = makeStore({ loadMessages: async () => [] })
    await store.controller.openSession(sessionOut())

    store.controller.markUserSent('What shipped this week?', SENT_SOURCES)
    expect(store.controller.visibleMessages.value).toHaveLength(1)

    await store.controller.openSession(sessionOut({ id: 's2' }))

    expect(store.controller.visibleMessages.value).toEqual([])
  })
})

describe('thread store sidebar refresh', () => {
  it('asks for a refreshed record once the run is under way and again when it settles', async () => {
    const gate = deferred()
    const onSessionChanged = vi.fn()
    const store = makeStore({
      onSessionChanged,
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          await gate.promise
          yield started
          yield progress('Done github: Found 3 github results.', 'github', 'done', 3)
          yield {
            event: 'done',
            data: { request_id: 'r1', message_id: 4, run_id: 9, path: 'digest' },
          }
        })(),
    })

    await store.controller.openSession(sessionOut())
    onSessionChanged.mockClear()

    const sending = store.lifecycle.send('s1', { content: 'digest please' })
    expect(store.controller.snapshot.value.state).toBe('streaming')
    // The server has no request row for this run yet, so there is nothing to pick up.
    expect(onSessionChanged).not.toHaveBeenCalled()

    gate.resolve()
    await sending

    expect(onSessionChanged).toHaveBeenCalledTimes(2)
  })

  it('asks for a refreshed record when a run is cancelled', async () => {
    const onSessionChanged = vi.fn()
    const store = makeStore({
      onSessionChanged,
      loadMessages: async () => [],
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
    onSessionChanged.mockClear()

    await store.lifecycle.send('s1', { content: 'digest please' })

    expect(onSessionChanged).toHaveBeenCalledTimes(2)
  })
})

describe('thread store run ownership', () => {
  it('keeps a running request out of the conversation that is not running it', async () => {
    const hold = deferred()
    const poll = deferred<RequestOut>()
    const store = makeStore({
      loadMessages: async () => [],
      getRequest: async () => poll.promise,
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Calling github…', 'github', 'running')
          await hold.promise
        })(),
    })

    await store.controller.openSession(sessionOut({ id: 's1' }))
    const sending = store.lifecycle.send('s1', { content: 'what is new?' })
    await waitFor(() => store.controller.run.value !== null)

    // The other conversation shows neither the run card nor the busy state the
    // composer reads, so a request of its own can start while the first one runs.
    await store.controller.openSession(sessionOut({ id: 's2' }))

    expect(store.controller.run.value).toBeNull()
    expect(store.controller.snapshot.value.state).toBe('idle')

    // Coming back to the running conversation picks its request up again.
    void store.controller.openSession(sessionOut({ id: 's1', active_request_id: 'r1' }))
    await waitFor(() => store.controller.snapshot.value.state === 'reconnecting')

    expect(store.controller.run.value?.reconnect).not.toBeNull()

    poll.resolve(requestOut({ status: 'succeeded' }))
    hold.resolve()
    await sending
  })

  it('does not show another conversation the failure that ended while it was open', async () => {
    const gate = deferred()
    const store = makeStore({
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          yield started
          await gate.promise
          yield {
            event: 'error',
            data: {
              request_id: 'r1',
              code: 'workflow_error',
              message: 'Digest generation failed.',
              correlation_id: 'c1',
            },
          } satisfies SseEvent
        })(),
    })

    await store.controller.openSession(sessionOut({ id: 's1' }))
    const sending = store.lifecycle.send('s1', { content: 'digest please' })
    await waitFor(() => store.controller.snapshot.value.state === 'streaming')

    await store.controller.openSession(sessionOut({ id: 's2' }))
    gate.resolve()
    await sending

    expect(store.controller.alert.value).toBeNull()
  })
})

describe('thread store exhausted polling', () => {
  it('offers to keep polling, and polls the request again when asked', async () => {
    const polls: string[] = []
    const store = makeStore({
      loadMessages: async () => [],
      post: async () => events([started]),
      getRequest: async (_sessionId, requestId) => {
        polls.push(requestId)
        return requestOut({ status: polls.length === 1 ? 'active' : 'succeeded' })
      },
    })

    await store.controller.openSession(sessionOut())
    await store.lifecycle.send('s1', { content: 'digest please' })

    expect(store.controller.snapshot.value.state).toBe('failed')
    expect(store.controller.alert.value).toEqual({
      kind: 'failed',
      message: 'The request failed.',
      canRunAgain: true,
      canRetryPoll: true,
    })

    await store.controller.retryPoll()

    expect(polls).toEqual(['r1', 'r1'])
    expect(store.controller.snapshot.value.state).toBe('succeeded')
  })

  it('does not offer polling once the outcome is known', async () => {
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

    expect(store.controller.alert.value?.canRetryPoll).toBeUndefined()
  })
})

describe('thread store requested outcomes', () => {
  it('shows the interrupted alert for a request that ended that way', async () => {
    const store = makeStore({
      loadMessages: async () => [],
      getRequest: async () => requestOut({ status: 'interrupted' }),
    })

    await store.controller.openSession(sessionOut({ active_request_id: 'r1' }))

    expect(store.controller.alert.value).toEqual({
      kind: 'interrupted',
      message: 'This request was interrupted by a restart',
      canRunAgain: true,
    })
  })
})

describe('thread store session sync', () => {
  it('takes a refreshed record into the live run without reloading the transcript', async () => {
    const hold = deferred()
    const loadMessages = vi.fn<ThreadDeps['loadMessages']>(async () => ({
      messages: [],
      nextCursor: null,
    }))
    const store = makeStore({
      loadMessages,
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Calling juya…', 'juya', 'running')
          await hold.promise
        })(),
    })
    await store.controller.openSession(sessionOut({ connector_names: ['juya', 'github'] }))
    const sending = store.lifecycle.send('s1', { content: 'what is new?' })
    await waitFor(() => store.controller.run.value !== null)
    loadMessages.mockClear()

    store.controller.syncSession(sessionOut({ connector_names: ['zhihu'] }))

    expect(store.controller.run.value?.steps.map((step) => step.source)).toEqual(['zhihu', 'juya'])
    expect(loadMessages).not.toHaveBeenCalled()

    hold.resolve()
    await sending
  })

  it('ignores a record for a conversation that is not open', async () => {
    const store = makeStore({ loadMessages: async () => [] })
    await store.controller.openSession(sessionOut({ connector_names: ['juya'] }))

    store.controller.syncSession(sessionOut({ id: 's2', connector_names: ['zhihu'] }))

    expect(store.controller.session.value?.connector_names).toEqual(['juya'])
  })
})

describe('thread store live run clocks', () => {  it('stamps the run start and each finished source from the local clock', async () => {
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

    await store.controller.openSession(sessionOut())
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

    await store.controller.openSession(sessionOut())
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

describe('thread store sent sources', () => {
  it('chips the question, then the row the backend persisted for it', async () => {
    const gate = deferred()
    const store = makeStore({
      loadMessages: async () => [
        message({ id: 1, sequence: 1, content: 'What shipped this week?' }),
      ],
      post: async () =>
        (async function* generate() {
          yield started
          await gate.promise
          yield {
            event: 'done',
            data: { request_id: 'r1', message_id: 2, run_id: 9, path: 'digest' },
          }
        })(),
    })
    await store.controller.openSession(sessionOut())

    store.controller.markUserSent('What shipped this week?', SENT_SOURCES)

    const pending = store.controller.visibleMessages.value.find(
      (item) => item.id === PENDING_MESSAGE_ID,
    )
    expect(pending?.chips).toEqual({
      sources: [
        { kind: 'juya', label: 'Juya' },
        { kind: 'github', label: 'GitHub' },
      ],
      perSource: 5,
    })

    const sending = store.lifecycle.send('s1', { content: 'What shipped this week?' })
    await waitFor(() => store.controller.snapshot.value.requestId === 'r1')
    gate.resolve()
    await sending
    await waitFor(() => store.controller.visibleMessages.value.length === 1)

    // The reloaded row is the same question, so it keeps the chips of the send.
    expect(store.controller.visibleMessages.value[0]?.id).toBe(1)
    expect(store.controller.visibleMessages.value[0]?.chips?.perSource).toBe(5)
  })

  it('leaves a question that was already in the transcript plain', async () => {
    const store = makeStore({
      loadMessages: async () => [
        message({ id: 1, sequence: 1, content: 'Loaded from the server' }),
      ],
    })

    await store.controller.openSession(sessionOut())

    expect(store.controller.visibleMessages.value[0]?.chips).toBeUndefined()
  })

  it('keeps the chips when the conversation is opened again in this page session', async () => {
    const store = makeStore({
      loadMessages: async (sessionId) =>
        sessionId === 's1' ? [message({ id: 1, sequence: 1, content: 'Asked here' })] : [],
      post: async () =>
        (async function* generate() {
          yield started
          yield {
            event: 'done',
            data: { request_id: 'r1', message_id: 2, run_id: 9, path: 'digest' },
          }
        })(),
    })
    await store.controller.openSession(sessionOut())
    store.controller.markUserSent('Asked here', { names: ['juya'], perSource: 5 })
    await store.lifecycle.send('s1', { content: 'Asked here' })

    await store.controller.openSession(sessionOut({ id: 's2' }))
    expect(store.controller.visibleMessages.value).toEqual([])

    await store.controller.openSession(sessionOut())

    expect(store.controller.visibleMessages.value[0]?.chips?.perSource).toBe(5)
  })
})

describe('thread store older messages', () => {
  it('keeps the cursor the loaded page carries', async () => {
    const store = makeStore({
      loadMessages: async () => ({ messages: [], nextCursor: 'older-1' }),
    })

    await store.controller.openSession(sessionOut())

    expect(store.controller.nextCursor.value).toBe('older-1')
  })

  it('prepends the older page in reading order without repeating a row', async () => {
    const asked: (string | null | undefined)[] = []
    const store = makeStore({
      loadMessages: async (_sessionId, cursor) => {
        asked.push(cursor)
        if (cursor === undefined || cursor === null) {
          return {
            messages: [
              message({ id: 3, sequence: 3, role: 'assistant', content: 'Newest' }),
              message({ id: 2, sequence: 2, content: 'Second' }),
            ],
            nextCursor: 'older-1',
          }
        }
        return {
          // The page boundary repeats the oldest row the first page carried.
          messages: [
            message({ id: 1, sequence: 1, content: 'First' }),
            message({ id: 2, sequence: 2, content: 'Second' }),
          ],
          nextCursor: null,
        }
      },
    })

    await store.controller.openSession(sessionOut())
    expect(store.controller.messages.value.map((item) => item.text)).toEqual([
      'Second',
      'Newest',
    ])

    await store.controller.loadOlder()

    expect(asked).toEqual([undefined, 'older-1'])
    expect(store.controller.messages.value.map((item) => item.text)).toEqual([
      'First',
      'Second',
      'Newest',
    ])
    expect(store.controller.nextCursor.value).toBeNull()
  })

  it('asks for nothing once the transcript is complete', async () => {
    const asked: (string | null | undefined)[] = []
    const store = makeStore({
      loadMessages: async (_sessionId, cursor) => {
        asked.push(cursor)
        return { messages: [], nextCursor: null }
      },
    })
    await store.controller.openSession(sessionOut())

    await store.controller.loadOlder()

    expect(asked).toEqual([undefined])
  })

  it('drops the older page of a conversation that was left behind', async () => {
    const gate = deferred<MessagePage>()
    const store = makeStore({
      loadMessages: async (_sessionId, cursor) => {
        if (cursor === undefined || cursor === null) {
          return { messages: [], nextCursor: 'older-1' }
        }
        return gate.promise
      },
    })
    await store.controller.openSession(sessionOut())

    const loading = store.controller.loadOlder()
    await store.controller.openSession(sessionOut({ id: 's2' }))
    gate.resolve({ messages: [message({ id: 9, sequence: 9, content: 'Older' })], nextCursor: null })
    await loading

    expect(store.controller.messages.value).toEqual([])
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

/** A follow-up answer: the streamed text, then the terminal `done` the store waits on. */
const followUpDelta: SseEvent = {
  event: 'delta',
  data: { text: 'Alpha beta gamma delta' },
}

const followUpDone: SseEvent = {
  event: 'done',
  data: { request_id: 'r1', message_id: 3, run_id: null, path: 'followup' },
}

/** The structured reply a digest run sends before it ends. */
const digestPayload: SseEvent = {
  event: 'digest',
  data: {
    run_id: 9,
    digest_id: 12,
    digest: { generated_at: '2026-10-01T20:04:00Z', entries: [] },
    markdown: '# digest',
    warnings: [],
    errors: [],
  },
}

const digestDone: SseEvent = {
  event: 'done',
  data: { request_id: 'r1', message_id: 4, run_id: 9, path: 'digest' },
}

/** The row the backend persists for that digest. */
function persistedDigest(): MessageOut {
  return message({
    id: 4,
    sequence: 4,
    role: 'assistant',
    content: 'Digest generated.',
    run_id: 9,
    digest_id: 12,
    digest: { generated_at: '2026-10-01T20:04:00Z', entries: [] },
  })
}

describe('thread store live digest', () => {
  it('shows the digest event while the run is still open', async () => {
    const hold = deferred()
    const store = makeStore({
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Done github: Found 3 github results.', 'github', 'done', 3)
          yield digestPayload
          await hold.promise
          yield digestDone
        })(),
    })

    await store.controller.openSession(sessionOut())
    const sending = store.lifecycle.send('s1', { content: 'digest please' })
    await waitFor(() => store.controller.liveDigest.value !== null)

    expect(store.controller.snapshot.value.state).toBe('streaming')
    expect(store.controller.liveDigest.value?.ref).toBe('d12')
    expect(store.controller.liveDigest.value?.generatedAt).toBe('2026-10-01T20:04:00Z')

    hold.resolve()
    await sending
    await waitFor(() => store.controller.liveDigest.value === null)

    expect(store.controller.run.value).toBeNull()
  })

  it('never shows the live digest and the persisted one at the same time', async () => {
    const store = makeStore({
      loadMessages: async () => [persistedDigest()],
      post: async () => events([started, digestPayload, digestDone]),
    })

    await store.controller.openSession(sessionOut())
    await store.lifecycle.send('s1', { content: 'digest please' })
    await waitFor(() => store.controller.liveDigest.value === null)

    const digests = store.controller.visibleMessages.value.filter(
      (item) => item.kind === 'digest',
    )

    expect(digests).toHaveLength(1)
    expect(store.controller.liveDigest.value).toBeNull()
  })

  it('drops the live digest when another conversation is opened', async () => {
    const hold = deferred()
    const store = makeStore({
      loadMessages: async () => [],
      post: async () =>
        (async function* generate() {
          yield started
          yield progress('Done github: Found 3 github results.', 'github', 'done', 3)
          yield digestPayload
          await hold.promise
          yield digestDone
        })(),
    })

    await store.controller.openSession(sessionOut())
    const sending = store.lifecycle.send('s1', { content: 'digest please' })
    await waitFor(() => store.controller.liveDigest.value !== null)

    await store.controller.openSession(sessionOut({ id: 's2' }))

    expect(store.controller.liveDigest.value).toBeNull()

    hold.resolve()
    await sending
  })
})

describe('thread store streamed follow-up reply', () => {
  /** Run a follow-up through its stream and stop the moment it reaches the hold. */
  async function heldAfterFollowUp() {
    const gate = deferred()
    const loadMessages = vi.fn<ThreadDeps['loadMessages']>(async () => ({
      messages: [],
      nextCursor: null,
    }))
    const store = makeStore({
      loadMessages,
      post: async () =>
        (async function* generate() {
          yield started
          yield followUpDelta
          await gate.promise
          yield followUpDone
        })(),
    })

    await store.controller.openSession(sessionOut())
    loadMessages.mockClear()

    store.controller.markUserSent('Why is it quantized?', SENT_SOURCES)
    const sending = store.lifecycle.send('s1', { content: 'Why is it quantized?' })
    await waitFor(() => store.controller.run.value?.streamText === 'Alpha beta gamma delta')

    gate.resolve()
    await sending
    await waitFor(() => store.controller.run.value?.ended === true)

    return { controller: store.controller, loadMessages }
  }

  it('stays up with the pending question until the reveal catches up', async () => {
    const { controller, loadMessages } = await heldAfterFollowUp()

    expect(controller.run.value?.ended).toBe(true)
    expect(controller.run.value?.streamText).toBe('Alpha beta gamma delta')
    expect(loadMessages).not.toHaveBeenCalled()
    expect(controller.visibleMessages.value.map((item) => item.text)).toEqual([
      'Why is it quantized?',
    ])
  })

  it('takes the persisted row once the reveal catches up', async () => {
    const { controller, loadMessages } = await heldAfterFollowUp()

    controller.revealFinished()
    await waitFor(() => loadMessages.mock.calls.length > 0)

    expect(loadMessages).toHaveBeenCalledWith('s1')
    expect(controller.run.value).toBeNull()
    expect(controller.visibleMessages.value).toEqual([])
  })

  it('brings the finished reply back when the next question is sent mid-reveal', async () => {
    const gate = deferred()
    const stalled = deferred()
    let calls = 0
    const loadMessages = vi.fn<ThreadDeps['loadMessages']>(async () => ({
      messages: [],
      nextCursor: null,
    }))
    const store = makeStore({
      loadMessages,
      post: async () => {
        calls += 1
        if (calls > 1) {
          return (async function* generate() {
            yield started
            await stalled.promise
          })()
        }
        return (async function* generate() {
          yield started
          yield followUpDelta
          await gate.promise
          yield followUpDone
        })()
      },
    })

    await store.controller.openSession(sessionOut())
    store.controller.markUserSent('Why is it quantized?', SENT_SOURCES)
    const first = store.lifecycle.send('s1', { content: 'Why is it quantized?' })
    await waitFor(() => store.controller.run.value?.streamText === 'Alpha beta gamma delta')

    gate.resolve()
    await first
    expect(store.controller.run.value?.ended).toBe(true)

    loadMessages.mockClear()
    store.controller.markUserSent('One more thing', SENT_SOURCES)
    void store.lifecycle.send('s1', { content: 'One more thing' })
    await waitFor(() => loadMessages.mock.calls.length > 0)

    expect(loadMessages).toHaveBeenCalledWith('s1')
    expect(store.controller.visibleMessages.value.map((item) => item.text)).toEqual([
      'One more thing',
    ])
  })

  it('drops the hold when another conversation is opened', async () => {
    const { controller, loadMessages } = await heldAfterFollowUp()

    await controller.openSession(sessionOut({ id: 's2' }))
    loadMessages.mockClear()

    controller.revealFinished()
    await new Promise((resolve) => {
      setTimeout(resolve, 0)
    })

    expect(loadMessages).not.toHaveBeenCalled()
  })
})

describe('thread store streamed digest reply', () => {
  it('hands the transcript over as soon as the run succeeds', async () => {
    const loadMessages = vi.fn<ThreadDeps['loadMessages']>(async () => ({
      messages: [],
      nextCursor: null,
    }))
    const store = makeStore({
      loadMessages,
      post: async () =>
        events([
          started,
          progress('Done github: Found 3 github results.', 'github', 'done', 3),
          {
            event: 'done',
            data: { request_id: 'r1', message_id: 4, run_id: 9, path: 'digest' },
          },
        ]),
    })

    await store.controller.openSession(sessionOut())
    loadMessages.mockClear()

    store.controller.markUserSent('Digest please', SENT_SOURCES)
    await store.lifecycle.send('s1', { content: 'Digest please' })
    await waitFor(() => loadMessages.mock.calls.length > 0)

    expect(loadMessages).toHaveBeenCalledWith('s1')
    expect(store.controller.run.value).toBeNull()
    expect(store.controller.visibleMessages.value).toEqual([])
  })
})
