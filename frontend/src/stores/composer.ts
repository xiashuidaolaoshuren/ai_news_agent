import { defineStore, storeToRefs } from 'pinia'
import { computed, getCurrentScope, onScopeDispose, ref, watch, type Ref } from 'vue'

import type { SessionOut, SessionPatch } from '@/api/generated/types.gen'
import {
  patchSessionApiV1SessionsSessionIdPatch,
  sourcesApiV1SourcesGet,
} from '@/api/generated/sdk.gen'
import type { RequestLifecycle, RequestSnapshot } from '@/api/lifecycle'
import { setupApiClient } from '@/api/setupClient'
import { useSessionsStore } from '@/stores/sessions'
import { useThreadStore } from '@/stores/thread'
import {
  COUNT_INVALID,
  COUNT_MAX,
  COUNT_MIN,
  DEFAULT_ITEMS_PER_SOURCE,
  PREFS_FAILED,
  SEND_FAILED,
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

/** Server calls and shared state the composer needs, injected for tests. */
export interface ComposerDeps {
  loadSources(): Promise<SourceOption[]>
  session(): SessionOut | null
  draft: Ref<string>
  snapshot(): RequestSnapshot
  lifecycle: RequestLifecycle
  patchPrefs(sessionId: string, body: SessionPatch): Promise<SessionOut>
  applySession(next: SessionOut): void
  runAgain(): void
  markUserSent(text: string, sources: SentSourcesInput): void
  newId(): string
}

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
    async loadSources(): Promise<SourceOption[]> {
      const result = await sourcesApiV1SourcesGet()
      return parseSources(result.data ?? null)
    },
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
    markUserSent: (text, sources) => {
      thread.markUserSent(text, sources)
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
  const selected = ref<string[]>([])
  const count = ref(String(DEFAULT_ITEMS_PER_SOURCE))
  const errors = ref<ComposerErrors>({})

  /** Bumped whenever something outside the composer asks for the caret. */
  const focusToken = ref(0)

  /** Take the session's stored preferences, falling back to the catalog defaults. */
  function syncPrefs(): void {
    const prefs = prefsFor(deps.session(), sources.value)
    selected.value = [...prefs.selected]
    count.value = prefs.count
    errors.value = {}
  }

  async function load(): Promise<void> {
    try {
      sources.value = await deps.loadSources()
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

  /** A request owns this conversation while its stream is open or being polled. */
  const active = computed(() => {
    const state = deps.snapshot().state
    return state === 'streaming' || state === 'reconnecting'
  })

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
      count: count.value,
      errors: errors.value,
      busy: active.value,
      notice: notice.value,
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
    const items = Number(count.value)
    if (sessionId === undefined || selected.value.length === 0) {
      return false
    }
    if (!Number.isInteger(items) || items < COUNT_MIN || items > COUNT_MAX) {
      return false
    }
    try {
      const next = await deps.patchPrefs(sessionId, {
        connector_names: [...selected.value],
        items_per_source: items,
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

  /** Take a typed count once the field is committed, and persist it when usable. */
  async function commitCount(raw: string): Promise<void> {
    count.value = raw
    const value = Number(raw)
    if (!Number.isInteger(value) || value < COUNT_MIN || value > COUNT_MAX) {
      errors.value = { ...errors.value, count: COUNT_INVALID }
      return
    }
    clearError('count')
    await persistPrefs()
  }

  /** One stepper click, clamped into the spec's range. */
  async function stepCount(delta: number): Promise<void> {
    const current = Number(count.value)
    const base = Number.isFinite(current) ? Math.round(current) : COUNT_MIN
    const before = count.value
    count.value = String(Math.min(COUNT_MAX, Math.max(COUNT_MIN, base + delta)))
    clearError('count')
    if (count.value === before) {
      return
    }
    await persistPrefs()
  }

  /** Validate, then start one run. Returns false when nothing was sent. */
  function send(): boolean {
    if (active.value) {
      sendBlocked.value = true
      return false
    }
    const draft = deps.draft.value
    const nextErrors = validateComposer({
      text: draft,
      selected: selected.value,
      count: count.value,
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
    const content = draft.trim()
    deps.draft.value = ''
    deps.markUserSent(content, {
      names: [...selected.value],
      perSource: Number(count.value),
    })
    void deps.lifecycle
      .send(sessionId, {
        content,
        client_request_id: deps.newId(),
        juya_item_mode: 'stories',
      })
      .catch(() => {
        errors.value = { send: SEND_FAILED }
      })
    return true
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

  /** "Ask a follow-up" on one entry. */
  function prefillFollowUp(title: string): void {
    prefill(`Tell me more about “${title}”: what it is and how I could try it.`)
  }

  /** "Run again" refills from the last user message; it never resends. */
  function runAgain(): void {
    deps.runAgain()
    focusToken.value += 1
  }

  return {
    vm,
    sources,
    selected,
    count,
    errors,
    focusToken,
    load,
    send,
    cancel,
    setText,
    prefill,
    prefillFollowUp,
    runAgain,
    toggleSource,
    commitCount,
    stepCount,
  }
}

export type ComposerController = ReturnType<typeof createComposerController>

export const useComposerStore = defineStore('composer', () =>
  createComposerController(defaultComposerDeps()),
)
