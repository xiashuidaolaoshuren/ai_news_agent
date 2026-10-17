import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type {
  SessionListPage,
  SessionOut,
  SessionSearchPageOut,
} from '@/api/generated/types.gen'
import {
  createSessionApiV1SessionsPost,
  deleteSessionApiV1SessionsSessionIdDelete,
  healthApiV1HealthGet,
  listSessionsApiV1SessionsGet,
  patchSessionApiV1SessionsSessionIdPatch,
  searchApiV1SessionsSearchGet,
} from '@/api/generated/sdk.gen'
import { setupApiClient } from '@/api/setupClient'
import { toSessionHitVm, type SessionHitVm } from '@/vm/history'
import { groupSessions, type SessionGroupVm } from '@/vm/session'

/** Result of a delete call, normalized so the store never reads the raw client shape. */
export interface DeleteSessionResult {
  ok: boolean
  status: number
  code: string | null
}

/** Server calls the sessions store needs, injected so tests need no HTTP layer. */
export interface SessionsDeps {
  listSessions(params: { limit: number; cursor: string | null }): Promise<SessionListPage>
  searchSessions(params: {
    q: string
    limit: number
    cursor: string | null
  }): Promise<SessionSearchPageOut>
  createSession(): Promise<SessionOut>
  renameSession(sessionId: string, title: string): Promise<SessionOut>
  deleteSession(sessionId: string): Promise<DeleteSessionResult>
  loadHealth(): Promise<{ fake: boolean }>
}

export interface SessionsOptions {
  now?: () => Date
  pageLimit?: number
}

const DEFAULT_PAGE_LIMIT = 50

/** Copy shown when a delete is refused because the session is running. */
export const BUSY_DELETE_MESSAGE = 'Cancel the running request first'

/** The code the API returns in `detail` when a session has an active request. */
const SESSION_BUSY_CODE = 'session_busy'

function toDeleteResult(result: {
  response?: Response
  error?: unknown
}): DeleteSessionResult {
  const status = result.response?.status ?? 0
  if (result.response?.ok === true) {
    return { ok: true, status, code: null }
  }
  const detail = (result.error as { detail?: unknown } | undefined)?.detail
  let code: string | null = null
  if (typeof detail === 'object' && detail !== null && 'code' in detail) {
    const raw = (detail as { code?: unknown }).code
    if (typeof raw === 'string') {
      code = raw
    }
  }
  return { ok: false, status, code }
}

/** Production dependencies wired to the generated OpenAPI client. */
export function defaultSessionsDeps(): SessionsDeps {
  setupApiClient()
  return {
    async listSessions(params): Promise<SessionListPage> {
      const result = await listSessionsApiV1SessionsGet({
        query: { limit: params.limit, cursor: params.cursor },
      })
      if (result.data === undefined) {
        throw new Error(`session list failed with status ${result.response?.status ?? 0}`)
      }
      return result.data
    },
    async searchSessions(params): Promise<SessionSearchPageOut> {
      const result = await searchApiV1SessionsSearchGet({
        query: { q: params.q, limit: params.limit, cursor: params.cursor },
      })
      if (result.data === undefined) {
        throw new Error(`session search failed with status ${result.response?.status ?? 0}`)
      }
      return result.data
    },
    async createSession(): Promise<SessionOut> {
      const result = await createSessionApiV1SessionsPost()
      if (result.data === undefined) {
        throw new Error(`session create failed with status ${result.response?.status ?? 0}`)
      }
      return result.data
    },
    async renameSession(sessionId, title): Promise<SessionOut> {
      const result = await patchSessionApiV1SessionsSessionIdPatch({
        path: { session_id: sessionId },
        body: { title },
      })
      if (result.data === undefined) {
        throw new Error(`session rename failed with status ${result.response?.status ?? 0}`)
      }
      return result.data
    },
    async deleteSession(sessionId): Promise<DeleteSessionResult> {
      const result = await deleteSessionApiV1SessionsSessionIdDelete({
        path: { session_id: sessionId },
      })
      return toDeleteResult(result)
    },
    async loadHealth(): Promise<{ fake: boolean }> {
      const result = await healthApiV1HealthGet()
      const body = result.data as { fake?: unknown } | undefined
      return { fake: body?.fake === true }
    },
  }
}

/** Reactive sessions state and actions. Shared by the Pinia store and the tests. */
export function createSessionsController(
  deps: SessionsDeps,
  options: SessionsOptions = {},
) {
  const now = options.now ?? (() => new Date())
  const pageLimit = options.pageLimit ?? DEFAULT_PAGE_LIMIT

  const sessions = ref<SessionOut[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const activeId = ref<string | null>(null)
  const flashId = ref<string | null>(null)
  /** The row that has just been added and is animating open, per the prototype. */
  const enterId = ref<string | null>(null)
  const renamingId = ref<string | null>(null)
  const deleteId = ref<string | null>(null)
  const deleteError = ref<string | null>(null)
  const searchQuery = ref('')
  const hits = ref<SessionHitVm[]>([])
  const searching = ref(false)
  const fakeMode = ref(false)
  const reachable = ref(true)

  const groups = computed<SessionGroupVm[]>(() => groupSessions(sessions.value, now()))

  /** Replace one session in place, keeping list order. */
  function replaceSession(next: SessionOut): void {
    const index = sessions.value.findIndex((session) => session.id === next.id)
    if (index === -1) {
      sessions.value = [next, ...sessions.value]
      return
    }
    const copy = [...sessions.value]
    copy[index] = next
    sessions.value = copy
  }

  /** Read the session list from the first page to the last. */
  async function fetchSessions(): Promise<SessionOut[]> {
    const collected: SessionOut[] = []
    let cursor: string | null = null
    for (;;) {
      const page = await deps.listSessions({ limit: pageLimit, cursor })
      collected.push(...page.sessions)
      cursor = page.next_cursor
      if (cursor === null) {
        break
      }
    }
    return collected
  }

  async function loadSessions(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const collected = await fetchSessions()
      sessions.value = collected
      if (activeId.value === null && collected.length > 0) {
        activeId.value = collected[0]?.id ?? null
      }
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : 'Failed to load sessions'
    } finally {
      loading.value = false
    }
  }

  /**
   * Re-read the list after a run or a preference save changed a session's title,
   * digest count, or active request. The selection stays on the conversation the
   * user is reading, the loading flag stays down so the sidebar never flashes a
   * spinner mid-run, and a failed refresh keeps the list it already had.
   */
  async function refreshSessions(): Promise<void> {
    try {
      sessions.value = await fetchSessions()
    } catch {
      return
    }
  }

  /** A session is reusable when it is untitled and has produced no digests. */
  function isEmptySession(session: SessionOut): boolean {
    return session.title === null && (session.digest_count ?? 0) === 0
  }

  async function createOrReuse(): Promise<void> {
    // The local record goes stale as soon as a run titles the conversation or adds a
    // digest, so ask the server before deciding whether anything is reusable.
    await refreshSessions()
    const empty = sessions.value.find(isEmptySession)
    if (empty !== undefined) {
      activeId.value = empty.id
      flashId.value = empty.id
      return
    }
    const created = await deps.createSession()
    sessions.value = [created, ...sessions.value]
    activeId.value = created.id
    enterId.value = created.id
    flashId.value = created.id
  }

  async function rename(sessionId: string, title: string): Promise<void> {
    const next = await deps.renameSession(sessionId, title)
    replaceSession(next)
    renamingId.value = null
  }

  function cancelRename(): void {
    renamingId.value = null
  }

  /** Select a conversation in the sidebar. */
  function openSession(sessionId: string): void {
    activeId.value = sessionId
    deleteId.value = null
    deleteError.value = null
  }

  /** Open the inline rename form for one row. */
  function requestRename(sessionId: string): void {
    renamingId.value = sessionId
    deleteId.value = null
    deleteError.value = null
  }

  function requestDelete(sessionId: string): void {
    deleteId.value = sessionId
    deleteError.value = null
    renamingId.value = null
  }

  function cancelDelete(): void {
    deleteId.value = null
    deleteError.value = null
  }

  async function confirmDelete(sessionId: string): Promise<void> {
    const result = await deps.deleteSession(sessionId)
    deleteId.value = null
    if (!result.ok) {
      deleteError.value =
        result.code === SESSION_BUSY_CODE
          ? BUSY_DELETE_MESSAGE
          : 'Could not delete this conversation.'
      return
    }
    deleteError.value = null
    sessions.value = sessions.value.filter((session) => session.id !== sessionId)
    if (activeId.value === sessionId) {
      activeId.value = sessions.value[0]?.id ?? null
    }
    if (flashId.value === sessionId) {
      flashId.value = null
    }
    if (enterId.value === sessionId) {
      enterId.value = null
    }
  }

  async function search(query: string): Promise<void> {
    const trimmed = query.trim()
    searchQuery.value = trimmed
    if (trimmed === '') {
      hits.value = []
      searching.value = false
      return
    }
    searching.value = true
    try {
      const page = await deps.searchSessions({ q: trimmed, limit: pageLimit, cursor: null })
      hits.value = page.hits.map(toSessionHitVm)
    } finally {
      searching.value = false
    }
  }

  async function loadHealth(): Promise<void> {
    try {
      const health = await deps.loadHealth()
      fakeMode.value = health.fake
      reachable.value = true
    } catch {
      fakeMode.value = false
      reachable.value = false
    }
  }

  const statusCopy = computed<string>(() => {
    if (!reachable.value) {
      return 'Backend unreachable'
    }
    return fakeMode.value
      ? 'Backend running in fake mode'
      : 'Backend connected · live sources'
  })

  return {
    sessions,
    loading,
    error,
    activeId,
    flashId,
    enterId,
    renamingId,
    deleteId,
    deleteError,
    searchQuery,
    hits,
    searching,
    fakeMode,
    reachable,
    statusCopy,
    groups,
    loadSessions,
    refreshSessions,
    createOrReuse,
    rename,
    cancelRename,
    openSession,
    requestRename,
    requestDelete,
    cancelDelete,
    confirmDelete,
    search,
    loadHealth,
    replaceSession,
  }
}

export type SessionsController = ReturnType<typeof createSessionsController>

export const useSessionsStore = defineStore('sessions', () =>
  createSessionsController(defaultSessionsDeps()),
)
