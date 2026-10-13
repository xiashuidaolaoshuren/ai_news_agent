import { defineStore } from 'pinia'
import { computed, ref, shallowRef, type Ref } from 'vue'

import type { MessageOut, SessionOut } from '@/api/generated/types.gen'
import { listMessagesApiV1SessionsSessionIdMessagesGet } from '@/api/generated/sdk.gen'
import {
  createRequestLifecycle,
  defaultLifecycleDeps,
  type LifecycleState,
  type RequestLifecycle,
  type RequestSnapshot,
} from '@/api/lifecycle'
import { setupApiClient } from '@/api/setupClient'
import { toMessageVm, toRequestStateVm, type MessageVm, type RequestStateVm } from '@/vm/session'
import {
  toCancelledVm,
  toRunVm,
  type CancelledVm,
  type RunProgress,
  type RunVm,
  type RunVmInput,
} from '@/vm/run'

/** How long the "Reconnected." banner stays before the reloaded messages replace it. */
const RECONNECTED_DWELL_MS = 1200

/** Server calls and ambient services the thread store needs, injected for tests. */
export interface ThreadDeps {
  loadMessages(sessionId: string): Promise<MessageOut[]>
  lifecycle: RequestLifecycle
  now(): Date
  schedule(handler: () => void, ms: number): void
}

/** Production dependencies wired to the generated client and the request lifecycle. */
export function defaultThreadDeps(): ThreadDeps {
  setupApiClient()
  return {
    async loadMessages(sessionId: string): Promise<MessageOut[]> {
      const result = await listMessagesApiV1SessionsSessionIdMessagesGet({
        path: { session_id: sessionId },
      })
      if (result.data === undefined) {
        throw new Error(`message list failed with status ${result.response?.status ?? 0}`)
      }
      return result.data.messages
    },
    lifecycle: createRequestLifecycle(defaultLifecycleDeps()),
    now: () => new Date(),
    schedule: (handler, ms) => {
      setTimeout(handler, ms)
    },
  }
}

/** Terminal lifecycle states, which end a run and settle its outcome. */
function isTerminalState(state: LifecycleState): boolean {
  return state === 'succeeded' || state === 'failed' || state === 'cancelled'
}

/** `20:14:07` local clock label for the live run's times. */
export function clockLabel(date: Date): string {
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((part) => String(part).padStart(2, '0'))
    .join(':')
}

/** Reactive thread state: the transcript, the live run, and its terminal outcome. */
export function createThreadController(deps: ThreadDeps) {
  const messages = ref<MessageVm[]>([])
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const session = shallowRef<SessionOut | null>(null)
  const draft = ref('')
  const snapshot = shallowRef<RequestSnapshot>(deps.lifecycle.state)
  const progressTimes = ref<string[]>([])
  const startedAt = ref<string | null>(null)
  const droppedAt = ref<string | null>(null)
  const endedAt = ref<string | null>(null)
  const reconnected = ref(false)

  const clock = () => clockLabel(deps.now())

  /** Drop the ambient clocks that belong to the previous request. */
  function resetRunClocks(): void {
    progressTimes.value = []
    startedAt.value = null
    droppedAt.value = null
    endedAt.value = null
    reconnected.value = false
  }

  deps.lifecycle.subscribe((next) => {
    const previous = snapshot.value
    const active = next.state === 'streaming' || next.state === 'reconnecting'
    const wasActive = previous.state === 'streaming' || previous.state === 'reconnecting'
    if (active && !wasActive) {
      resetRunClocks()
      startedAt.value = next.state === 'streaming' ? clock() : null
    }
    if (next.progress.length > progressTimes.value.length) {
      const added = next.progress.length - progressTimes.value.length
      progressTimes.value = [
        ...progressTimes.value,
        ...Array.from({ length: added }, () => clock()),
      ]
    }
    if (next.state === 'reconnecting' && previous.state !== 'reconnecting') {
      droppedAt.value = clock()
    }
    if (next.state === 'cancelled' && previous.state !== 'cancelled') {
      endedAt.value = clock()
    }
    if (previous.state === 'reconnecting' && next.state === 'succeeded') {
      reconnected.value = true
      deps.schedule(() => {
        reconnected.value = false
      }, RECONNECTED_DWELL_MS)
    }
    if (active) {
      reconnected.value = false
    }
    // The backend persists its own terminal row; refresh so the digest reply lands.
    if (!active && wasActive && isTerminalState(next.state)) {
      const sessionId = session.value?.id
      if (sessionId !== undefined) {
        void loadMessages(sessionId)
      }
    }
    snapshot.value = next
  })

  function runInput(): RunVmInput {
    const current = snapshot.value
    const progress: RunProgress[] = current.progress.map((event, index) => ({
      stage: event.stage,
      source: event.source ?? null,
      status: event.status ?? null,
      count: event.count ?? null,
      at: progressTimes.value[index] ?? null,
    }))
    return {
      state: current.state,
      progress,
      text: current.text,
      attempt: current.attempt,
      nextDelayMs: current.nextDelayMs,
      selectedSources: session.value?.connector_names ?? null,
      startedAt: startedAt.value,
      droppedAt: droppedAt.value,
      endedAt: endedAt.value,
      reconnected: reconnected.value,
    }
  }

  const run = computed<RunVm | null>(() => toRunVm(runInput()))
  const cancelled = computed<CancelledVm | null>(() => toCancelledVm(runInput()))

  /**
   * The live outcome occupies the last reply slot. The row the backend persists for
   * the same outcome reloads into the transcript, so hide that copy while the live
   * one is up rather than rendering the outcome twice.
   */
  const visibleMessages = computed<MessageVm[]>(() => {
    if (cancelled.value !== null) {
      return messages.value.filter((item) => item.kind !== 'cancelled')
    }
    const outcome = alert.value?.message ?? null
    if (outcome === null) {
      return messages.value
    }
    return messages.value.filter((item) => item.text !== outcome)
  })

  /**
   * A failed run shows the safe message with Run again. `interrupted` arrives as a
   * `failed` state, so the durable status picks the alert copy.
   */
  const alert = computed<RequestStateVm | null>(() => {
    const current = snapshot.value
    if (current.state !== 'failed') {
      return null
    }
    return toRequestStateVm({
      status: current.terminalStatus ?? 'failed',
      error_code: current.error?.code ?? null,
      error_message: current.error?.message ?? null,
    })
  })

  /** Render the transcript in reading order; the API pages newest first. */
  function toMessages(loaded: MessageOut[]): MessageVm[] {
    return [...loaded].sort((a, b) => a.sequence - b.sequence).map(toMessageVm)
  }

  async function loadMessages(sessionId: string): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      messages.value = toMessages(await deps.loadMessages(sessionId))
    } catch (caught) {
      loadError.value =
        caught instanceof Error ? caught.message : 'Failed to load this conversation'
    } finally {
      loading.value = false
    }
  }

  /**
   * Open one conversation. A session with an active request resumes straight into
   * the reconnecting state, as the spec requires after a page reload.
   */
  async function openSession(next: SessionOut | null): Promise<void> {
    const sameSession = next !== null && session.value?.id === next.id
    session.value = next
    if (sameSession) {
      return
    }
    messages.value = []
    loadError.value = null
    draft.value = ''
    if (next === null) {
      return
    }
    await loadMessages(next.id)
    const active = next.active_request_id ?? null
    if (active !== null) {
      await deps.lifecycle.resume(next.id, active)
    }
  }

  /** "Run again" refills the composer; it never resends by itself. */
  function runAgain(): void {
    const last = [...messages.value].reverse().find((message) => message.kind === 'user')
    draft.value = last?.text ?? ''
  }

  return {
    messages: messages as Ref<MessageVm[]>,
    visibleMessages,
    loading,
    loadError,
    session,
    draft,
    snapshot,
    run,
    cancelled,
    alert,
    lifecycle: deps.lifecycle,
    loadMessages,
    openSession,
    runAgain,
  }
}

export type ThreadController = ReturnType<typeof createThreadController>

export const useThreadStore = defineStore('thread', () =>
  createThreadController(defaultThreadDeps()),
)
