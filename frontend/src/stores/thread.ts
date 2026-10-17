import { defineStore } from 'pinia'
import { computed, ref, shallowRef, type Ref } from 'vue'

import type { MessageOut, SessionOut } from '@/api/generated/types.gen'
import { listMessagesApiV1SessionsSessionIdMessagesGet } from '@/api/generated/sdk.gen'
import {
  createRequestLifecycle,
  defaultLifecycleDeps,
  idleRequestSnapshot,
  type LifecycleState,
  type RequestLifecycle,
  type RequestSnapshot,
} from '@/api/lifecycle'
import { setupApiClient } from '@/api/setupClient'
import { prefersReducedMotion } from '@/lib/motion'
import { useSessionsStore } from '@/stores/sessions'
import { toDigestVm, type DigestVm } from '@/vm/digest'
import { toMessageVm, toRequestStateVm, toResolvedSourcesVm, toSentSourcesVm, type MessageVm, type RequestStateVm, type SentSourcesInput, type SentSourcesVm } from '@/vm/session'
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

/** The banner's own collapse time, from the prototype's shut-then-clear step. */
const RECONNECT_COLLAPSE_MS = 340

/** The id the transcript renders for the message the user just sent. */
export const PENDING_MESSAGE_ID = -1

/** One page of the transcript: the rows, and the cursor for the page before it. */
export interface MessagePage {
  messages: MessageOut[]
  nextCursor: string | null
}

/** Server calls and ambient services the thread store needs, injected for tests. */
export interface ThreadDeps {
  loadMessages(sessionId: string, cursor?: string | null): Promise<MessagePage>
  lifecycle: RequestLifecycle
  now(): Date
  schedule(handler: () => void, ms: number): void
  /**
   * Called when the server has changed something about the open session: the title
   * it assigned to the first message, its digest count, or the request it is running.
   */
  onSessionChanged?(): void
}

/** Production dependencies wired to the generated client and the request lifecycle. */
export function defaultThreadDeps(): ThreadDeps {
  setupApiClient()
  const sessions = useSessionsStore()
  return {
    async loadMessages(sessionId: string, cursor?: string | null): Promise<MessagePage> {
      const result = await listMessagesApiV1SessionsSessionIdMessagesGet({
        path: { session_id: sessionId },
        ...(cursor === undefined || cursor === null ? {} : { query: { cursor } }),
      })
      if (result.data === undefined) {
        throw new Error(`message list failed with status ${result.response?.status ?? 0}`)
      }
      return { messages: result.data.messages, nextCursor: result.data.next_cursor ?? null }
    },
    lifecycle: createRequestLifecycle(defaultLifecycleDeps()),
    now: () => new Date(),
    schedule: (handler, ms) => {
      setTimeout(handler, ms)
    },
    onSessionChanged: () => {
      void sessions.refreshSessions()
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
  const loadingOlder = ref(false)
  /** The cursor for the page before the oldest row on screen, or null at the start. */
  const nextCursor = ref<string | null>(null)
  const loadError = ref<string | null>(null)
  const session = shallowRef<SessionOut | null>(null)
  const draft = ref('')
  const pendingUser = ref<{ text: string; chips: SentSourcesVm } | null>(null)
  const freshIds = ref<number[]>([])
  const rawSnapshot = shallowRef<RequestSnapshot>(deps.lifecycle.state)
  const progressTimes = ref<string[]>([])
  const startedAt = ref<string | null>(null)
  const droppedAt = ref<string | null>(null)
  const endedAt = ref<string | null>(null)
  const reconnected = ref(false)
  const reconnectLeaving = ref(false)

  /**
   * The digest a run is streaming. It stands in for the reply between the `digest`
   * event and the reload that brings the row the backend persisted for it.
   */
  const liveDigest = ref<DigestVm | null>(null)

  /**
   * The sources of every question sent during this page session, by the id the
   * backend gave its row. Chips belong to those questions alone, so nothing that
   * was loaded from the server on its own has them.
   */
  const sentSources = ref<Map<number, SentSourcesVm>>(new Map())

  const clock = () => clockLabel(deps.now())

  /**
   * True when a run belongs to the conversation that is open.
   *
   * A request belongs to the conversation it was sent from, so another conversation
   * shows neither its card nor its outcome, and can start a request of its own.
   */
  function ownsRun(next: RequestSnapshot): boolean {
    if (next.sessionId === null) {
      return true
    }
    return next.sessionId === (session.value?.id ?? null)
  }

  /** The open conversation's run. Another conversation's run reads as idle. */
  const snapshot = computed<RequestSnapshot>(() =>
    ownsRun(rawSnapshot.value) ? rawSnapshot.value : idleRequestSnapshot(),
  )

  /** True while a finished reply's reveal is still catching up in the live slot. */
  const holding = ref(false)

  /** Drop the ambient clocks that belong to the previous request. */
  function resetRunClocks(): void {
    progressTimes.value = []
    startedAt.value = null
    droppedAt.value = null
    endedAt.value = null
    reconnected.value = false
    reconnectLeaving.value = false
    liveDigest.value = null
  }

  deps.lifecycle.subscribe((next) => {
    const previous = rawSnapshot.value
    const active = next.state === 'streaming' || next.state === 'reconnecting'
    // A run's clocks follow the conversation it was sent from; the sidebar refresh
    // follows it anywhere, because the list reports every conversation's request.
    const sameRun = previous.sessionId === next.sessionId
    const wasActive =
      sameRun && (previous.state === 'streaming' || previous.state === 'reconnecting')
    const settled = !active && wasActive && isTerminalState(next.state)
    if (next.state === 'streaming' && previous.requestId === null && next.requestId !== null) {
      // The server now holds this conversation's request row, so the sidebar can pick
      // up the title it assigned and show that the conversation is running.
      deps.onSessionChanged?.()
    }
    if (settled) {
      // The settled run carries the new digest count and no active request.
      deps.onSessionChanged?.()
    }
    if (ownsRun(next)) {
      if (active && !wasActive) {
        if (holding.value) {
          // A new question arrived while the last reply was still typing itself out.
          // Bring its persisted row back instead of leaving a hole in the transcript,
          // and leave the pending row alone: it now stands in for the new question.
          holding.value = false
          const heldSession = session.value?.id
          if (heldSession !== undefined) {
            void loadMessages(heldSession)
          }
        }
        resetRunClocks()
        startedAt.value = next.state === 'streaming' ? clock() : null
      }
      if (
        next.userMessageId !== null &&
        next.userMessageId !== previous.userMessageId &&
        pendingUser.value !== null
      ) {
        // The row the backend persisted for the question keeps the chips of what the
        // run actually resolved to, which can differ from the composer's selection.
        const nextSources = new Map(sentSources.value)
        if (next.intent !== null && next.intent !== 'digest') {
          nextSources.delete(next.userMessageId)
        } else if (next.request !== null) {
          nextSources.set(next.userMessageId, toResolvedSourcesVm(next.request))
        } else {
          nextSources.set(next.userMessageId, pendingUser.value.chips)
        }
        sentSources.value = nextSources
      }
      if (next.digest !== null) {
        // The `digest` event is the reply: show it now rather than waiting for `done`
        // and the reload that follows it.
        liveDigest.value = toDigestVm({
          digest: next.digest.digest,
          digestId: next.digest.digest_id,
          warnings: next.digest.warnings,
          connectorNames: session.value?.connector_names ?? null,
        })
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
      if (sameRun && previous.state === 'reconnecting' && next.state === 'succeeded') {
        reconnected.value = true
        reconnectLeaving.value = false
        // The banner collapses a beat before the reconnect is dropped, as the
        // prototype's shut-then-clear step does. With reduced motion it vanishes
        // whole at the end of the dwell instead.
        const lead = prefersReducedMotion()
          ? RECONNECTED_DWELL_MS
          : RECONNECTED_DWELL_MS - RECONNECT_COLLAPSE_MS
        const dwellSession = session.value?.id ?? null
        deps.schedule(() => {
          if ((session.value?.id ?? null) !== dwellSession) {
            return
          }
          reconnectLeaving.value = true
        }, lead)
        deps.schedule(() => {
          if ((session.value?.id ?? null) !== dwellSession) {
            return
          }
          reconnectLeaving.value = false
          reconnected.value = false
        }, RECONNECTED_DWELL_MS)
      }
      if (active) {
        reconnected.value = false
        reconnectLeaving.value = false
      }
      // The backend persists its own terminal row; refresh so the digest reply lands.
      if (settled) {
        // A follow-up reply types itself out, and the server finishes sending it long
        // before the reveal catches up, so the live reply keeps the slot until then.
        const live = next.state === 'succeeded' ? toRunVm(runInput(next, true)) : null
        if (live?.mode === 'followup') {
          holding.value = true
        } else {
          settleRun()
        }
      }
    }
    rawSnapshot.value = next
  })

  /**
   * Take the row the backend persisted for the finished request, and stop standing
   * in for it with the pending question. Held back while a reveal is still running.
   */
  async function settleRun(): Promise<void> {
    holding.value = false
    pendingUser.value = null
    const sessionId = session.value?.id
    if (sessionId !== undefined) {
      await loadMessages(sessionId, { markFresh: true })
    }
    // The reloaded transcript carries the digest now, so the live copy stands down.
    liveDigest.value = null
  }

  /** The live reply's reveal caught up, so the transcript can take the row over. */
  function revealFinished(): void {
    if (!holding.value) {
      return
    }
    settleRun()
  }

  function runInput(
    current: RequestSnapshot = snapshot.value,
    holds = holding.value,
  ): RunVmInput {
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
      reconnectLeaving: reconnectLeaving.value,
      holding: holds,
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
    const pending =
      pendingUser.value === null
        ? []
        : [
            {
              id: PENDING_MESSAGE_ID,
              sequence: PENDING_MESSAGE_ID,
              kind: 'user' as const,
              text: pendingUser.value.text,
              createdAt: '',
              chips: pendingUser.value.chips,
              warnings: [],
            },
          ]
    const cancelledOutcome = cancelled.value !== null
    const outcome = cancelledOutcome ? null : (alert.value?.message ?? null)
    const digestRef = liveDigest.value?.ref ?? null
    const rows = messages.value.map(withChips).filter((item) => {
      if (cancelledOutcome && item.kind === 'cancelled') {
        return false
      }
      if (outcome !== null && item.text === outcome) {
        return false
      }
      return !(digestRef !== null && item.digest?.ref === digestRef)
    })
    return [...rows, ...pending]
  })

  /** A question sent in this page session carries the sources it was sent with. */
  function withChips(message: MessageVm): MessageVm {
    if (message.kind !== 'user') {
      return message
    }
    const chips = sentSources.value.get(message.id)
    return chips === undefined ? message : { ...message, chips }
  }

  /**
   * A failed run shows the safe message with Run again. `interrupted` arrives as a
   * `failed` state, so the durable status picks the alert copy. While the outcome is
   * unknown the alert also offers to poll the request again.
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
      canRetryPoll: current.terminalStatus === null && current.requestId !== null,
    })
  })

  /** Render the transcript in reading order; the API pages newest first. */
  function toMessages(loaded: MessageOut[]): MessageVm[] {
    return [...loaded].sort((a, b) => a.sequence - b.sequence).map(toMessageVm)
  }

  /**
   * Load the transcript. A reload after a run marks the rows it adds as fresh so
   * the reveal animation plays for the reply that just landed; opening a
   * conversation shows it still.
   */
  async function loadMessages(
    sessionId: string,
    options: { markFresh?: boolean } = {},
  ): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const page = await deps.loadMessages(sessionId)
      // The user may have opened another conversation while this was in flight.
      if ((session.value?.id ?? null) !== sessionId) {
        return
      }
      const next = toMessages(page.messages)
      const known = new Set(messages.value.map((message) => message.id))
      messages.value = next
      nextCursor.value = page.nextCursor
      freshIds.value =
        options.markFresh === true
          ? next
              .filter((message) => message.kind !== 'user' && !known.has(message.id))
              .map((message) => message.id)
          : []
    } catch (caught) {
      if ((session.value?.id ?? null) === sessionId) {
        loadError.value =
          caught instanceof Error ? caught.message : 'Failed to load this conversation'
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Load the page before the oldest row on screen and put it in front. Rows the
   * transcript already carries are dropped, since a page boundary can repeat one.
   */
  async function loadOlder(): Promise<void> {
    const cursor = nextCursor.value
    const sessionId = session.value?.id
    if (cursor === null || sessionId === undefined || loadingOlder.value) {
      return
    }
    loadingOlder.value = true
    try {
      const page = await deps.loadMessages(sessionId, cursor)
      if ((session.value?.id ?? null) !== sessionId) {
        return
      }
      nextCursor.value = page.nextCursor
      const known = new Set(messages.value.map((message) => message.id))
      const older = page.messages
        .filter((message) => !known.has(message.id))
        .map(toMessageVm)
      messages.value = [...older, ...messages.value].sort((a, b) => a.sequence - b.sequence)
    } catch (caught) {
      if ((session.value?.id ?? null) === sessionId) {
        loadError.value =
          caught instanceof Error ? caught.message : 'Failed to load this conversation'
      }
    } finally {
      loadingOlder.value = false
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
    pendingUser.value = null
    freshIds.value = []
    nextCursor.value = null
    // A digest that was streaming in the conversation being left behind belongs to
    // it, not to this one.
    liveDigest.value = null
    // A reply that was still typing out in the conversation being left behind is
    // gone with it; its transcript reloads from the server on its own.
    holding.value = false
    if (next === null) {
      return
    }
    await loadMessages(next.id)
    const active = next.active_request_id ?? null
    if (active !== null) {
      await deps.lifecycle.resume(next.id, active)
    }
  }

  /**
   * Take a refreshed record for the conversation that is open. The sidebar reloads
   * the list after a run or a preference save, and the run card reads its sources
   * from here; the transcript and the live run themselves stay as they are.
   */
  function syncSession(next: SessionOut | null): void {
    if (next === null || session.value?.id !== next.id) {
      return
    }
    session.value = next
  }

  /** "Run again" refills the composer; it never resends by itself. */
  function runAgain(): void {
    const last = [...messages.value].reverse().find((message) => message.kind === 'user')
    draft.value = last?.text ?? ''
  }

  /**
   * Poll the request once more after the attempts ran out. The server may still be
   * running it, and the outcome is what ends the alert.
   */
  async function retryPoll(): Promise<void> {
    const requestId = rawSnapshot.value.requestId
    const sessionId = session.value?.id
    if (requestId === null || sessionId === undefined) {
      return
    }
    await deps.lifecycle.resume(sessionId, requestId)
  }

  /**
   * The message the user just sent, with the sources it goes out with. It stands in
   * for the row the backend persists until the terminal reload brings that row back
   * with the reply.
   */
  function markUserSent(text: string, sources: SentSourcesInput): void {
    pendingUser.value = { text, chips: toSentSourcesVm(sources) }
  }

  return {
    messages: messages as Ref<MessageVm[]>,
    visibleMessages,
    freshIds,
    loading,
    loadingOlder,
    nextCursor,
    loadError,
    session,
    draft,
    snapshot,
    run,
    cancelled,
    alert,
    liveDigest,
    lifecycle: deps.lifecycle,
    loadMessages,
    loadOlder,
    openSession,
    syncSession,
    runAgain,
    retryPoll,
    markUserSent,
    revealFinished,
  }
}

export type ThreadController = ReturnType<typeof createThreadController>

export const useThreadStore = defineStore('thread', () =>
  createThreadController(defaultThreadDeps()),
)
