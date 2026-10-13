import type {
  DigestPayload,
  ErrorPayload,
  PostMessageBody,
  ProgressPayload,
  RequestOut,
} from '@/api/generated/types.gen'
import {
  cancelRequestApiV1SessionsSessionIdRequestsRequestIdCancelPost,
  getRequestStatusApiV1SessionsSessionIdRequestsRequestIdGet,
  listMessagesApiV1SessionsSessionIdMessagesGet,
} from '@/api/generated/sdk.gen'
import type { SseEvent } from '@/api/sse'
import { SseHttpError, postMessageStream } from '@/api/sse'
import { setupApiClient } from '@/api/setupClient'

/** Lifecycle states from the web frontend spec. */
export type LifecycleState =
  | 'idle'
  | 'streaming'
  | 'reconnecting'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

/** Blocking 409 detail codes returned before a stream starts. */
export type BlockedCode = 'session_busy' | 'request_in_progress'

/** Durable request status once the run reaches an outcome. */
export type TerminalStatus = 'succeeded' | 'failed' | 'cancelled' | 'interrupted'

export interface RequestSnapshot {
  state: LifecycleState
  requestId: string | null
  text: string
  progress: ProgressPayload[]
  digest: DigestPayload | null
  error: ErrorPayload | null
  attempt: number
  nextDelayMs: number | null
  blocked: BlockedCode | null
  /** Terminal request status, so an interruption is distinguishable from a failure. */
  terminalStatus: TerminalStatus | null
}

export interface LifecycleDeps {
  post(sessionId: string, body: PostMessageBody): Promise<AsyncIterable<SseEvent>>
  getRequest(sessionId: string, requestId: string): Promise<RequestOut>
  cancel(sessionId: string, requestId: string): Promise<number>
  reloadMessages(sessionId: string): Promise<unknown>
  sleep(ms: number): Promise<void>
  backoffMs?: number[]
}

export interface RequestLifecycle {
  readonly state: RequestSnapshot
  send(sessionId: string, body: PostMessageBody): Promise<void>
  cancel(): Promise<void>
  resume(sessionId: string, requestId: string): Promise<void>
  subscribe(listener: (snapshot: RequestSnapshot) => void): () => void
}

const DEFAULT_BACKOFF_MS = [1000, 2000, 4000, 8000, 16000]

function idleSnapshot(): RequestSnapshot {
  return {
    state: 'idle',
    requestId: null,
    text: '',
    progress: [],
    digest: null,
    error: null,
    attempt: 0,
    nextDelayMs: null,
    blocked: null,
    terminalStatus: null,
  }
}

function isTerminal(state: LifecycleState): boolean {
  return state === 'succeeded' || state === 'failed' || state === 'cancelled'
}

/** Narrow a durable request status to the terminal statuses the UI models. */
function toTerminalStatus(status: string): TerminalStatus | null {
  return status === 'succeeded' ||
    status === 'failed' ||
    status === 'cancelled' ||
    status === 'interrupted'
    ? status
    : null
}

function isBlockedCode(code: string | null): code is BlockedCode {
  return code === 'session_busy' || code === 'request_in_progress'
}

/** Own the request state machine for one conversation. */
export function createRequestLifecycle(deps: LifecycleDeps): RequestLifecycle {
  const backoffMs = deps.backoffMs ?? DEFAULT_BACKOFF_MS
  let snapshot: RequestSnapshot = idleSnapshot()
  let currentSessionId: string | null = null
  let runToken = 0
  let settleTerminal: (() => void) | null = null
  let terminalReached: Promise<void> = Promise.resolve()
  const listeners = new Set<(snapshot: RequestSnapshot) => void>()

  function emit(patch: Partial<RequestSnapshot>): void {
    snapshot = { ...snapshot, ...patch }
    for (const listener of [...listeners]) {
      listener(snapshot)
    }
    if (isTerminal(snapshot.state)) {
      settleTerminal?.()
    }
  }

  function beginRun(): number {
    runToken += 1
    terminalReached = new Promise<void>((resolve) => {
      settleTerminal = resolve
    })
    return runToken
  }

  /** True once a newer run has started, so this one must stop mutating state. */
  function isSuperseded(token: number): boolean {
    return token !== runToken
  }

  function subscribe(listener: (snapshot: RequestSnapshot) => void): () => void {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }

  async function pumpStream(
    sessionId: string,
    body: PostMessageBody,
    token: number,
  ): Promise<void> {
    const stream = await deps.post(sessionId, body)
    for await (const event of stream) {
      if (isSuperseded(token)) {
        return
      }
      switch (event.event) {
        case 'started':
          emit({ requestId: event.data.request_id })
          break
        case 'progress':
          emit({ progress: [...snapshot.progress, event.data] })
          break
        case 'delta':
          emit({ text: event.data.text })
          break
        case 'digest':
          emit({ digest: event.data })
          break
        case 'done':
          emit({ state: 'succeeded', terminalStatus: 'succeeded' })
          break
        case 'error':
          emit({
            error: event.data,
            state: event.data.code === 'cancelled' ? 'cancelled' : 'failed',
            terminalStatus: toTerminalStatus(event.data.code ?? '') ?? 'failed',
          })
          break
        default:
          break
      }
    }
    if (!isTerminal(snapshot.state) && !isSuperseded(token)) {
      await reconnect(sessionId, 1, token)
    }
  }

  /** Poll the request with backoff until it reaches a terminal status. */
  async function reconnect(
    sessionId: string,
    startAttempt = 1,
    token: number = runToken,
  ): Promise<void> {
    const requestId = snapshot.requestId
    if (requestId === null) {
      emit({ state: 'failed' })
      return
    }
    for (let attempt = startAttempt; attempt <= backoffMs.length; attempt += 1) {
      if (isSuperseded(token)) {
        return
      }
      const delay = backoffMs[attempt - 1] ?? backoffMs[backoffMs.length - 1] ?? 0
      emit({ state: 'reconnecting', attempt, nextDelayMs: delay })
      await deps.sleep(delay)
      if (isSuperseded(token)) {
        return
      }
      const record = await deps.getRequest(sessionId, requestId)
      if (isSuperseded(token)) {
        return
      }
      if (record.status !== 'active') {
        await settleFromStatus(sessionId, record.status)
        return
      }
    }
    emit({ state: 'failed', nextDelayMs: null })
  }

  async function settleFromStatus(sessionId: string, status: string): Promise<void> {
    const terminalStatus = toTerminalStatus(status)
    if (status === 'succeeded') {
      emit({ state: 'succeeded', attempt: 0, nextDelayMs: null, terminalStatus })
      await deps.reloadMessages(sessionId)
      return
    }
    if (status === 'cancelled') {
      emit({ state: 'cancelled', attempt: 0, nextDelayMs: null, terminalStatus })
      await deps.reloadMessages(sessionId)
      return
    }
    if (status === 'failed' || status === 'interrupted') {
      emit({ state: 'failed', attempt: 0, nextDelayMs: null, terminalStatus })
      await deps.reloadMessages(sessionId)
    }
  }

  async function send(sessionId: string, body: PostMessageBody): Promise<void> {
    currentSessionId = sessionId
    const token = beginRun()
    emit({ ...idleSnapshot(), state: 'streaming' })
    try {
      await pumpStream(sessionId, body, token)
    } catch (error) {
      if (
        error instanceof SseHttpError &&
        error.status === 409 &&
        isBlockedCode(error.code) &&
        !isSuperseded(token)
      ) {
        emit({ ...idleSnapshot(), blocked: error.code })
        return
      }
      throw error
    }
  }

  async function cancel(): Promise<void> {
    const requestId = snapshot.requestId
    const sessionId = currentSessionId
    if (requestId === null || sessionId === null || isTerminal(snapshot.state)) {
      return
    }
    const status = await deps.cancel(sessionId, requestId)
    if (status === 202) {
      await terminalReached
      return
    }
    const record = await deps.getRequest(sessionId, requestId)
    await settleFromStatus(sessionId, record.status)
  }

  async function resume(sessionId: string, requestId: string): Promise<void> {
    currentSessionId = sessionId
    const token = beginRun()
    emit({ ...idleSnapshot(), requestId, state: 'reconnecting' })
    await reconnect(sessionId, 1, token)
  }

  return {
    get state() {
      return snapshot
    },
    send,
    cancel,
    resume,
    subscribe,
  }
}

/** Production dependencies wired to the generated OpenAPI client. */
export function defaultLifecycleDeps(): LifecycleDeps {
  setupApiClient()
  return {
    post: (sessionId, body) => postMessageStream(sessionId, body),
    async getRequest(sessionId, requestId): Promise<RequestOut> {
      const result = await getRequestStatusApiV1SessionsSessionIdRequestsRequestIdGet({
        path: { session_id: sessionId, request_id: requestId },
      })
      if (result.data === undefined) {
        throw new Error(
          `request status failed with status ${result.response?.status ?? 0}`,
        )
      }
      return result.data
    },
    async cancel(sessionId, requestId): Promise<number> {
      const result = await cancelRequestApiV1SessionsSessionIdRequestsRequestIdCancelPost({
        path: { session_id: sessionId, request_id: requestId },
      })
      return result.response?.status ?? 0
    },
    async reloadMessages(sessionId: string): Promise<unknown> {
      const result = await listMessagesApiV1SessionsSessionIdMessagesGet({
        path: { session_id: sessionId },
      })
      return result.data
    },
    sleep: (ms: number) =>
      new Promise<void>((resolve) => {
        setTimeout(resolve, ms)
      }),
  }
}
