import { defineStore, storeToRefs } from 'pinia'
import { computed, getCurrentScope, onScopeDispose, ref, watch, type Ref } from 'vue'

import type { PostMessageBody, SessionOut, SessionPatch } from '@/api/generated/types.gen'
import {
  patchSessionApiV1SessionsSessionIdPatch,
  sourcesApiV1SourcesGet,
} from '@/api/generated/sdk.gen'
import type { RequestLifecycle, RequestSnapshot } from '@/api/lifecycle'
import { SseHttpError } from '@/api/sse'
import { setupApiClient } from '@/api/setupClient'
import { useSessionsStore } from '@/stores/sessions'
import { useThreadStore } from '@/stores/thread'
import {
  PREFS_FAILED,
  SEND_FAILED,
  FOLLOWUP_TARGET_UNAVAILABLE,
  REPEAT_UNAVAILABLE,
  parseHiddenSources,
  parseSources,
  prefsFor,
  toComposerVm,
  validateComposer,
  type ComposerErrors,
  type ComposerNotice,
  type ComposerVm,
  type SourceOption,
} from '@/vm/composer'
import type { SentSourcesInput } from '@/vm/session'
import type { RefVm } from '@/vm/types'

/** One `GET /sources` payload: the visible catalog and the names it hides. */
export interface SourceCatalog {
  sources: SourceOption[]
  hidden: string[]
}

/** Server calls and shared state the composer needs, injected for tests. */
export interface ComposerDeps {
  loadCatalog(): Promise<SourceCatalog>
  countsSeen(): boolean
  writeCountsSeen(): void
  /** The transcript failed to load, so a send is refused. */
  loadFailed(): boolean
  /** A Juya request is waiting for Continue or Cancel. */
  confirmPending(): boolean
  session(): SessionOut | null
  draft: Ref<string>
  snapshot(): RequestSnapshot
  lifecycle: RequestLifecycle
  patchPrefs(sessionId: string, body: SessionPatch): Promise<SessionOut>
  applySession(next: SessionOut): void
  runAgain(): void
  markUserSent(text: string, sources: SentSourcesInput, ref?: RefVm | null): void
  newId(): string
}

/** One-time notice: new requests use the global source counts from Settings. */
const COUNTS_SEEN_KEY = 'anra-counts-seen'

/** A UUID for `client_request_id`, with a fallback for older runtimes. */
function randomId(): string {
  const source = globalThis.crypto
  if (source !== undefined && typeof source.randomUUID === 'function') {
    return source.randomUUID()
  }
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/** Production dependencies wired to the generated client and the app stores. */
export function defaultComposerDeps(): ComposerDeps {
  setupApiClient()
  const thread = useThreadStore()
  const sessions = useSessionsStore()
  const { draft } = storeToRefs(thread)
  return {
    async loadCatalog(): Promise<SourceCatalog> {
      const result = await sourcesApiV1SourcesGet()
      return {
        sources: parseSources(result.data ?? null),
        hidden: parseHiddenSources(result.data ?? null),
      }
    },
    countsSeen: () => {
      try {
        return localStorage.getItem(COUNTS_SEEN_KEY) === '1'
      } catch {
        return false
      }
    },
    writeCountsSeen: () => {
      try {
        localStorage.setItem(COUNTS_SEEN_KEY, '1')
      } catch {
        // A private window that blocks storage still hides the notice for this page.
      }
    },
    loadFailed: () => thread.loadError !== null,
    confirmPending: () =>
      thread.visibleMessages.some((message) => message.juyaConfirm !== undefined),
    session: () => thread.session,
    draft,
    snapshot: () => thread.snapshot,
    lifecycle: thread.lifecycle,
    async patchPrefs(sessionId, body): Promise<SessionOut> {
      const result = await patchSessionApiV1SessionsSessionIdPatch({
        path: { session_id: sessionId },
        body,
      })
      if (result.data === undefined) {
        throw new Error(`session update failed with status ${result.response?.status ?? 0}`)
      }
      return result.data
    },
    applySession: (next) => {
      sessions.replaceSession(next)
    },
    runAgain: () => {
      thread.runAgain()
    },
    markUserSent: (text, sources, ref) => {
      thread.markUserSent(text, sources, ref)
    },
    newId: randomId,
  }
}

/**
 * Reactive composer state. The text lives in the thread store's draft, so Run
 * again, a suggestion, and "Ask a follow-up" all prefill the same field.
 */
export function createComposerController(deps: ComposerDeps) {
  const sources = ref<SourceOption[]>([])
  /** Names the catalog hides; the display drops them without writing that back. */
  const hidden = ref<string[]>([])
  const selected = ref<string[]>([])
  const errors = ref<ComposerErrors>({})
  /** Follow-up target for "Ask about this" messages; cleared after send. */
  const targetRef = ref<RefVm | null>(null)

  /** The one-time count notice, reactive so a dismissal hides it at once. */
  const countsSeen = ref(deps.countsSeen())

  /** Bumped whenever something outside the composer asks for the caret. */
  const focusToken = ref(0)

  /** Take the session's stored preferences, falling back to the catalog defaults. */
  function syncPrefs(): void {
    const prefs = prefsFor(deps.session(), sources.value, hidden.value)
    selected.value = [...prefs.selected]
    errors.value = {}
    targetRef.value = null
  }

  /** One `GET /sources` call supplies both the visible catalog and the hidden names. */
  async function load(): Promise<void> {
    try {
      const catalog = await deps.loadCatalog()
      sources.value = catalog.sources
      hidden.value = catalog.hidden
    } catch {
      sources.value = []
    }
    syncPrefs()
  }

  // A different conversation carries its own preferences. Stopped with the store's
  // effect scope; a bare controller (tests) has none, so guard the hook.
  const stopWatch = watch(() => deps.session()?.id ?? null, syncPrefs)
  if (getCurrentScope() !== undefined) {
    onScopeDispose(stopWatch)
  }

  const sendBlocked = ref(false)

  /** Set when a send hits an unanswered Juya confirmation. */
  const confirmBlocked = ref(false)

  /** The prototype's note after Cancel; cleared by the next send. */
  const confirmCancelled = ref<string | null>(null)

  /** A request owns this conversation while its stream is open or being polled. */
  const active = computed(() => {
    const state = deps.snapshot().state
    return state === 'streaming' || state === 'reconnecting'
  })

  const confirmPending = computed(() => deps.confirmPending())

  // The confirmation was answered (or the conversation changed), so the refusal note goes.
  watch(
    confirmPending,
    (pending) => {
      if (!pending) {
        confirmBlocked.value = false
      }
    },
    { flush: 'sync' },
  )

  /** The notice above the textarea; a blocked send outranks the running notice. */
  const notice = computed<ComposerNotice>(() => {
    const current = deps.snapshot()
    if (current.blocked !== null) {
      return 'blocked'
    }
    if (active.value && sendBlocked.value) {
      return 'blocked'
    }
    if (current.state === 'reconnecting') {
      return 'reconnecting'
    }
    if (current.state === 'streaming') {
      return 'running'
    }
    return 'none'
  })

  // The blocked-while-busy notice belongs to the run that refused the send.
  watch(
    active,
    (isActive) => {
      if (!isActive) {
        sendBlocked.value = false
      }
    },
    { flush: 'sync' },
  )

  const vm = computed<ComposerVm>(() =>
    toComposerVm({
      text: deps.draft.value,
      sources: sources.value,
      selected: selected.value,
      errors: errors.value,
      busy: active.value,
      notice: notice.value,
      ref: targetRef.value,
      countsSeen: countsSeen.value,
      loadFailed: deps.loadFailed(),
      confirmPending: confirmPending.value && confirmBlocked.value,
      confirmCancelled: confirmCancelled.value,
    }),
  )

  /** Drop one error once the field that owns it is usable again. */
  function clearError(key: keyof ComposerErrors): void {
    if (errors.value[key] === undefined) {
      return
    }
    const next = { ...errors.value }
    delete next[key]
    errors.value = next
  }

  /**
   * Persist the current preferences. The backend refuses an empty source list or
   * a count outside 1-20, so an unusable draft is never patched.
   */
  async function persistPrefs(): Promise<boolean> {
    const sessionId = deps.session()?.id
    if (sessionId === undefined || selected.value.length === 0) {
      return false
    }
    try {
      const next = await deps.patchPrefs(sessionId, {
        connector_names: [...selected.value],
      })
      deps.applySession(next)
      clearError('prefs')
      return true
    } catch {
      errors.value = { ...errors.value, prefs: PREFS_FAILED }
      return false
    }
  }

  /** Toggle one source checkbox, keeping the catalog order, then persist. */
  async function toggleSource(name: string): Promise<void> {
    const on = selected.value.includes(name)
    selected.value = sources.value
      .filter((option) => (option.name === name ? !on : selected.value.includes(option.name)))
      .map((option) => option.name)
    if (selected.value.length > 0) {
      clearError('sources')
    }
    await persistPrefs()
  }

  function followupTargetPayload(ref: RefVm): NonNullable<PostMessageBody['followup_target']> {
    return { digest_id: ref.digestId, display_rank: ref.rank }
  }

  function isFollowupTargetHttpError(caught: unknown): boolean {
    if (!(caught instanceof SseHttpError) || caught.status !== 400) {
      return false
    }
    const raw = `${caught.code ?? ''} ${caught.message}`.toLowerCase()
    return raw.includes('follow-up target') || raw.includes('followup target')
  }

  function isRepeatHttpError(caught: unknown): boolean {
    return (
      caught instanceof SseHttpError &&
      caught.status === 400 &&
      (caught.code === 'repeat_resolution_missing' || caught.code === 'repeat_source_unknown')
    )
  }

  function handleSendFailure(caught: unknown): void {
    if (isFollowupTargetHttpError(caught)) {
      targetRef.value = null
      errors.value = { send: FOLLOWUP_TARGET_UNAVAILABLE }
      return
    }
    if (isRepeatHttpError(caught)) {
      errors.value = { send: REPEAT_UNAVAILABLE }
      return
    }
    errors.value = { send: SEND_FAILED }
  }

  /** Validate, then start one run. Returns false when nothing was sent. */
  function send(): boolean {
    if (active.value) {
      sendBlocked.value = true
      return false
    }
    if (deps.loadFailed()) {
      return false
    }
    if (confirmPending.value) {
      confirmBlocked.value = true
      return false
    }
    const draftText = deps.draft.value
    const nextErrors = validateComposer({
      text: draftText,
      selected: selected.value,
    })
    if (Object.keys(nextErrors).length > 0) {
      errors.value = nextErrors
      return false
    }
    const sessionId = deps.session()?.id
    if (sessionId === undefined) {
      return false
    }
    errors.value = {}
    sendBlocked.value = false
    confirmCancelled.value = null
    const content = draftText.trim()
    deps.draft.value = ''
    const ref = targetRef.value
    targetRef.value = null
    const body: PostMessageBody = {
      content,
      client_request_id: deps.newId(),
      juya_item_mode: 'stories',
    }
    if (ref !== null) {
      body.followup_target = followupTargetPayload(ref)
      body.followup_action = 'ask'
    }
    deps.markUserSent(
      content,
      {
        names: [...selected.value],
        // The resolved request reports the global counts once the run starts.
        perSource: null,
      },
      ref ?? undefined,
    )
    void deps.lifecycle.send(sessionId, body).catch(handleSendFailure)
    return true
  }

  /** Send a deep-dive follow-up immediately for one digest entry. */
  function deepDive(ref: RefVm): boolean {
    if (active.value) {
      sendBlocked.value = true
      return false
    }
    const sessionId = deps.session()?.id
    if (sessionId === undefined) {
      return false
    }
    errors.value = {}
    sendBlocked.value = false
    const content = `Deep dive: ${ref.title}`
    const body: PostMessageBody = {
      content,
      client_request_id: deps.newId(),
      juya_item_mode: 'stories',
      followup_target: followupTargetPayload(ref),
      followup_action: 'deep_dive',
    }
    deps.markUserSent(
      content,
      {
        names: [...selected.value],
        // The resolved request reports the global counts once the run starts.
        perSource: null,
      },
      ref,
    )
    void deps.lifecycle.send(sessionId, body).catch(handleSendFailure)
    return true
  }

  /** Start a new run from a stored resolution, optionally on one replacement source. */
  function repeat(input: {
    userMessageId: number
    text: string
    sources: string[]
    perSource: number | null
    replaceSource?: string
  }): boolean {
    if (active.value) {
      sendBlocked.value = true
      return false
    }
    const sessionId = deps.session()?.id
    if (sessionId === undefined) {
      return false
    }
    errors.value = {}
    sendBlocked.value = false
    const body: PostMessageBody = {
      content: input.text,
      client_request_id: deps.newId(),
      juya_item_mode: 'stories',
      repeat_of_user_message_id: input.userMessageId,
    }
    if (input.replaceSource !== undefined) {
      body.replace_source = input.replaceSource
    }
    deps.markUserSent(input.text, {
      names: input.sources,
      perSource: input.perSource,
    })
    void deps.lifecycle.send(sessionId, body).catch(handleSendFailure)
    return true
  }

  /** Set the ask-about target and focus the composer (no send). */
  function askAbout(ref: RefVm): void {
    targetRef.value = ref
    deps.draft.value = ''
    clearError('text')
    focusToken.value += 1
  }

  function removeRef(): void {
    targetRef.value = null
  }

  /** Stop the run this conversation owns. */
  async function cancel(): Promise<void> {
    await deps.lifecycle.cancel()
  }

  /** Take the typed text, dropping the text error as soon as it is satisfied. */
  function setText(text: string): void {
    deps.draft.value = text
    if (text.trim() !== '') {
      clearError('text')
    }
  }

  /** Put text in the composer from elsewhere and hand the caret back to it. */
  function prefill(text: string): void {
    setText(text)
    focusToken.value += 1
  }

  /** “Run again” refills from the last user message; it never resends. */
  function runAgain(): void {
    deps.runAgain()
    focusToken.value += 1
  }

  /** Hide the one-time count notice for good and hand the caret back. */
  function dismissCounts(): void {
    deps.writeCountsSeen()
    countsSeen.value = true
    focusToken.value += 1
  }

  /**
   * The user cancelled the Juya confirmation. Say so in the composer, as the
   * prototype does; the next send clears the note.
   */
  function noteConfirmCancelled(): void {
    confirmCancelled.value =
      'Cancelled. No digest was written, and your request is back in the composer.'
  }

  return {
    vm,
    sources,
    selected,
    errors,
    focusToken,
    targetRef,
    load,
    send,
    deepDive,
    repeat,
    askAbout,
    removeRef,
    cancel,
    setText,
    prefill,
    runAgain,
    dismissCounts,
    noteConfirmCancelled,
    toggleSource,
  }
}

export type ComposerController = ReturnType<typeof createComposerController>

export const useComposerStore = defineStore('composer', () =>
  createComposerController(defaultComposerDeps()),
)
