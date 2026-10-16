import { describe, expect, it } from 'vitest'

import type { MessageOut, SessionOut } from '@/api/generated/types.gen'
import { groupSessions, toMessageVm, toRequestStateVm, toSessionVm } from '@/vm'

const CANCELLED_TEXT = 'The request was cancelled.'

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

describe('toMessageVm kinds', () => {
  it('marks a user message', () => {
    const vm = toMessageVm(message())

    expect(vm.kind).toBe('user')
    expect(vm.text).toBe('What shipped this week?')
    expect(vm.createdAt).toBe('2026-10-01T20:04:00Z')
    expect(vm.digest).toBeUndefined()
  })

  it('marks an assistant message with a digest as a digest reply', () => {
    const vm = toMessageVm(
      message({
        id: 2,
        sequence: 2,
        role: 'assistant',
        content: 'Digest',
        run_id: 4,
        digest_id: 15,
        digest: {
          generated_at: '2026-10-01T20:04:00Z',
          entries: [],
        },
      }),
    )

    expect(vm.kind).toBe('digest')
    expect(vm.digest?.ref).toBe('d15')
    expect(vm.digest?.itemCount).toBe(0)
  })

  it('marks a plain assistant reply as markdown', () => {
    const vm = toMessageVm(
      message({ id: 3, sequence: 3, role: 'assistant', content: '## Answer', run_id: null }),
    )

    expect(vm.kind).toBe('markdown')
    expect(vm.digest).toBeUndefined()
  })

  it('marks the cancelled reply', () => {
    const vm = toMessageVm(
      message({
        id: 4,
        sequence: 4,
        role: 'assistant',
        content: CANCELLED_TEXT,
        run_id: 5,
      }),
    )

    expect(vm.kind).toBe('cancelled')
    expect(vm.text).toBe(CANCELLED_TEXT)
  })

  it('carries the persisted connector warnings on a digest reply', () => {
    const vm = toMessageVm(
      message({
        id: 5,
        sequence: 5,
        role: 'assistant',
        digest_id: 15,
        digest: { generated_at: '2026-10-01T20:04:00Z', entries: [] },
        warnings: [{ connector: 'zhihu', code: 'no_items', message: 'No items.' }],
      }),
    )

    expect(vm.digest?.warnings).toEqual([
      { source: 'zhihu', label: 'Zhihu', code: 'no_items', message: 'No items.' },
    ])
  })
})

describe('toRequestStateVm', () => {
  it('surfaces a failed request with its safe message and Run again', () => {
    const vm = toRequestStateVm({
      status: 'failed',
      error_code: 'workflow_error',
      error_message: 'Something went wrong.',
    })

    expect(vm).toEqual({
      kind: 'failed',
      message: 'Something went wrong.',
      canRunAgain: true,
    })
  })

  it('surfaces an interrupted request with the restart copy', () => {
    const vm = toRequestStateVm({ status: 'interrupted', error_code: null, error_message: null })

    expect(vm).toEqual({
      kind: 'interrupted',
      message: 'This request was interrupted by a restart',
      canRunAgain: true,
    })
  })

  it('offers to keep polling while the outcome is still unknown', () => {
    const vm = toRequestStateVm({
      status: 'failed',
      error_code: null,
      error_message: null,
      canRetryPoll: true,
    })

    expect(vm).toEqual({
      kind: 'failed',
      message: 'The request failed.',
      canRunAgain: true,
      canRetryPoll: true,
    })
  })

  it('leaves the polling offer out of every other alert', () => {
    expect(
      toRequestStateVm({ status: 'interrupted', canRetryPoll: true }),
    ).toEqual({
      kind: 'interrupted',
      message: 'This request was interrupted by a restart',
      canRunAgain: true,
    })
    expect(toRequestStateVm({ status: 'failed', canRetryPoll: false })).toEqual({
      kind: 'failed',
      message: 'The request failed.',
      canRunAgain: true,
    })
  })

  it('has no state for a request that is not failed or interrupted', () => {
    expect(toRequestStateVm({ status: 'succeeded', error_code: null, error_message: null })).toBeNull()
    expect(toRequestStateVm({ status: 'active', error_code: null, error_message: null })).toBeNull()
    expect(toRequestStateVm({ status: 'cancelled', error_code: null, error_message: null })).toBeNull()
  })
})

const NOW = new Date('2026-10-01T21:00:00')

function session(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: 's1',
    title: 'Open models & agent tools',
    connector_names: null,
    items_per_source: null,
    created_at: '2026-10-01T20:00:00',
    updated_at: '2026-10-01T20:09:00',
    digest_count: 2,
    active_request_id: null,
    ...overrides,
  }
}

describe('toSessionVm', () => {
  it('maps the sidebar fields', () => {
    const vm = toSessionVm(session(), NOW)

    expect(vm).toMatchObject({
      id: 's1',
      title: 'Open models & agent tools',
      isUntitled: false,
      digestCount: 2,
      busy: false,
      timeLabel: '20:09',
      groupLabel: 'Today',
    })
  })

  it('names an untitled session and flags it as empty', () => {
    const vm = toSessionVm(session({ title: null }), NOW)

    expect(vm.title).toBe('New conversation')
    expect(vm.isUntitled).toBe(true)
  })

  it('treats a blank title as untitled', () => {
    const vm = toSessionVm(session({ title: '   ' }), NOW)

    expect(vm.title).toBe('New conversation')
    expect(vm.isUntitled).toBe(true)
  })

  it('is busy while a request is active', () => {
    expect(toSessionVm(session({ active_request_id: 'r1' }), NOW).busy).toBe(true)
    expect(toSessionVm(session({ active_request_id: null }), NOW).busy).toBe(false)
  })

  it('defaults a missing digest count to zero', () => {
    expect(toSessionVm(session({ digest_count: undefined }), NOW).digestCount).toBe(0)
  })

  it('labels an older session with its month and a day stamp', () => {
    const vm = toSessionVm(
      session({ updated_at: '2026-09-21T09:40:00', digest_count: 1 }),
      NOW,
    )

    expect(vm.groupLabel).toBe('September')
    expect(vm.timeLabel).toBe('Sep 21')
  })

  it('includes the year for a session from another year', () => {
    const vm = toSessionVm(session({ updated_at: '2025-12-31T10:00:00' }), NOW)

    expect(vm.groupLabel).toBe('December 2025')
  })
})

describe('groupSessions', () => {
  it('groups by recency with Today first and preserves the given order', () => {
    const groups = groupSessions(
      [
        session({ id: 's1', updated_at: '2026-10-01T20:09:00' }),
        session({ id: 's2', updated_at: '2026-10-01T20:12:00' }),
        session({ id: 's3', updated_at: '2026-09-21T09:40:00' }),
        session({ id: 's4', updated_at: '2026-09-20T10:15:00' }),
      ],
      NOW,
    )

    expect(groups.map((group) => group.label)).toEqual(['Today', 'September'])
    expect(groups[0]?.sessions.map((vm) => vm.id)).toEqual(['s1', 's2'])
    expect(groups[1]?.sessions.map((vm) => vm.id)).toEqual(['s3', 's4'])
  })

  it('returns no groups for no sessions', () => {
    expect(groupSessions([], NOW)).toEqual([])
  })
})
