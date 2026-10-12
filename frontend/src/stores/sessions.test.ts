import { describe, expect, it, vi } from 'vitest'

import type { SessionOut } from '@/api/generated/types.gen'
import {
  BUSY_DELETE_MESSAGE,
  createSessionsController,
  type SessionsDeps,
} from '@/stores/sessions'

function sessionOut(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: 's1',
    title: null,
    connector_names: null,
    items_per_source: null,
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
    digest_count: 0,
    active_request_id: null,
    ...overrides,
  }
}

function fakeDeps(overrides: Partial<SessionsDeps> = {}): SessionsDeps {
  return {
    listSessions: vi.fn(async () => ({ sessions: [], next_cursor: null })),
    searchSessions: vi.fn(async () => ({ hits: [], next_cursor: null })),
    createSession: vi.fn(async () => sessionOut()),
    renameSession: vi.fn(async (sessionId: string) => sessionOut({ id: sessionId })),
    deleteSession: vi.fn(async () => ({ ok: true, status: 204, code: null })),
    loadHealth: vi.fn(async () => ({ fake: false })),
    ...overrides,
  }
}

const NOW = () => new Date('2026-10-12T12:00:00Z')

describe('loadSessions', () => {
  it('follows next_cursor until the list is complete', async () => {
    const listSessions = vi
      .fn<SessionsDeps['listSessions']>()
      .mockResolvedValueOnce({
        sessions: [sessionOut({ id: 's2', title: 'Second' })],
        next_cursor: 'c1',
      })
      .mockResolvedValueOnce({
        sessions: [sessionOut({ id: 's1', title: 'First' })],
        next_cursor: null,
      })
    const store = createSessionsController(fakeDeps({ listSessions }), { now: NOW })

    await store.loadSessions()

    expect(store.sessions.value.map((session) => session.id)).toEqual(['s2', 's1'])
    expect(listSessions).toHaveBeenCalledTimes(2)
    expect(listSessions.mock.calls[1]?.[0]).toMatchObject({ cursor: 'c1' })
    expect(store.loading.value).toBe(false)
  })
})

describe('createOrReuse', () => {
  it('selects an existing empty session and flashes it without creating one', async () => {
    const createSession = vi.fn<SessionsDeps['createSession']>()
    const store = createSessionsController(fakeDeps({ createSession }), { now: NOW })
    await store.loadSessions()
    store.sessions.value = [
      sessionOut({ id: 's2', title: 'Earlier', digest_count: 2 }),
      sessionOut({ id: 's1', title: null, digest_count: 0 }),
    ]

    await store.createOrReuse()

    expect(createSession).not.toHaveBeenCalled()
    expect(store.activeId.value).toBe('s1')
    expect(store.flashId.value).toBe('s1')
  })

  it('creates a session only when no empty one exists', async () => {
    const created = sessionOut({ id: 's9', title: null, digest_count: 0 })
    const createSession = vi.fn<SessionsDeps['createSession']>(async () => created)
    const store = createSessionsController(fakeDeps({ createSession }), { now: NOW })
    await store.loadSessions()
    store.sessions.value = [sessionOut({ id: 's2', title: 'Earlier', digest_count: 2 })]

    await store.createOrReuse()

    expect(createSession).toHaveBeenCalledTimes(1)
    expect(store.sessions.value.map((session) => session.id)).toEqual(['s9', 's2'])
    expect(store.activeId.value).toBe('s9')
    expect(store.flashId.value).toBe('s9')
  })
})

describe('rename', () => {
  it('PATCHes the title and clears the editing row', async () => {
    const renamed = sessionOut({ id: 's1', title: 'Renamed' })
    const renameSession = vi.fn<SessionsDeps['renameSession']>(async () => renamed)
    const store = createSessionsController(fakeDeps({ renameSession }), { now: NOW })
    store.sessions.value = [sessionOut({ id: 's1', title: null })]
    store.renamingId.value = 's1'

    await store.rename('s1', 'Renamed')

    expect(renameSession).toHaveBeenCalledWith('s1', 'Renamed')
    expect(store.sessions.value[0]?.title).toBe('Renamed')
    expect(store.renamingId.value).toBeNull()
  })

  it('cancels on Escape without sending a request', async () => {
    const renameSession = vi.fn<SessionsDeps['renameSession']>()
    const store = createSessionsController(fakeDeps({ renameSession }), { now: NOW })
    store.sessions.value = [sessionOut({ id: 's1', title: 'Kept' })]
    store.renamingId.value = 's1'

    store.cancelRename()

    expect(renameSession).not.toHaveBeenCalled()
    expect(store.renamingId.value).toBeNull()
    expect(store.sessions.value[0]?.title).toBe('Kept')
  })
})

describe('confirmDelete', () => {
  it('removes the row and moves the selection when the active one goes', async () => {
    const store = createSessionsController(fakeDeps(), { now: NOW })
    store.sessions.value = [
      sessionOut({ id: 's2', title: 'Second' }),
      sessionOut({ id: 's1', title: 'First' }),
    ]
    store.activeId.value = 's2'
    store.deleteId.value = 's2'

    await store.confirmDelete('s2')

    expect(store.sessions.value.map((session) => session.id)).toEqual(['s1'])
    expect(store.activeId.value).toBe('s1')
    expect(store.deleteId.value).toBeNull()
  })

  it('keeps the session and explains why when the API reports it busy', async () => {
    const deleteSession = vi.fn<SessionsDeps['deleteSession']>(async () => ({
      ok: false,
      status: 409,
      code: 'session_busy',
    }))
    const store = createSessionsController(fakeDeps({ deleteSession }), { now: NOW })
    store.sessions.value = [sessionOut({ id: 's1', title: 'Running one' })]
    store.deleteId.value = 's1'

    await store.confirmDelete('s1')

    expect(store.sessions.value.map((session) => session.id)).toEqual(['s1'])
    expect(store.deleteId.value).toBeNull()
    expect(store.deleteError.value).toBe(BUSY_DELETE_MESSAGE)
  })
})

describe('search', () => {
  it('maps hits to match kind and excerpt', async () => {
    const searchSessions = vi.fn<SessionsDeps['searchSessions']>(async () => ({
      hits: [
        {
          session_id: 's1',
          title: 'Qwen notes',
          updated_at: '2026-10-12T10:00:00Z',
          match_kind: 'assistant',
          message_id: 12,
          excerpt: 'a brief on Qwen3',
        },
      ],
      next_cursor: null,
    }))
    const store = createSessionsController(fakeDeps({ searchSessions }), { now: NOW })

    await store.search('qwen')

    expect(searchSessions).toHaveBeenCalledTimes(1)
    expect(searchSessions.mock.calls[0]?.[0]).toMatchObject({ q: 'qwen' })
    expect(store.hits.value).toEqual([
      {
        sessionId: 's1',
        title: 'Qwen notes',
        matchKind: 'assistant',
        excerpt: 'a brief on Qwen3',
        updatedAt: '2026-10-12T10:00:00Z',
      },
    ])
    expect(store.searchQuery.value).toBe('qwen')
  })

  it('makes no request and clears hits for an empty query', async () => {
    const searchSessions = vi.fn<SessionsDeps['searchSessions']>()
    const store = createSessionsController(fakeDeps({ searchSessions }), { now: NOW })
    store.hits.value = [
      {
        sessionId: 's1',
        title: 'Old hit',
        matchKind: 'title',
        excerpt: null,
        updatedAt: '2026-10-12T10:00:00Z',
      },
    ]

    await store.search('   ')

    expect(searchSessions).not.toHaveBeenCalled()
    expect(store.hits.value).toEqual([])
  })
})

describe('loadHealth', () => {
  it('follows the fake flag and names the mode', async () => {
    const store = createSessionsController(
      fakeDeps({ loadHealth: vi.fn(async () => ({ fake: true })) }),
      { now: NOW },
    )

    await store.loadHealth()

    expect(store.fakeMode.value).toBe(true)
    expect(store.reachable.value).toBe(true)
    expect(store.statusCopy.value).toBe('Backend running in fake mode')
  })

  it('reports live sources when the backend is not fake', async () => {
    const store = createSessionsController(
      fakeDeps({ loadHealth: vi.fn(async () => ({ fake: false })) }),
      { now: NOW },
    )

    await store.loadHealth()

    expect(store.fakeMode.value).toBe(false)
    expect(store.statusCopy.value).toBe('Backend connected · live sources')
  })

  it('marks the backend unreachable when the call fails', async () => {
    const store = createSessionsController(
      fakeDeps({
        loadHealth: vi.fn(async () => {
          throw new Error('ECONNREFUSED')
        }),
      }),
      { now: NOW },
    )

    await store.loadHealth()

    expect(store.reachable.value).toBe(false)
    expect(store.statusCopy.value).toBe('Backend unreachable')
  })
})
