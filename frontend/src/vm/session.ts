import type {
  FollowupTarget,
  MessageOut,
  ResolvedRequestOut,
  SessionOut,
} from '@/api/generated/types.gen'
import { sourceKindOf, sourceLabel, toDigestVm, toWarningVm } from '@/vm/digest'
import type { DigestVm, WarningVm } from '@/vm/digest'
import { textOrNull } from '@/vm/entries'
import type { EntryKind, FollowupActionVm, RefVm } from '@/vm/types'

/** Exact assistant content the backend writes when a request is cancelled. */
export const CANCELLED_ASSISTANT_MESSAGE = 'The request was cancelled.'

/** Exact assistant content the backend writes when the digest workflow fails. */
export const WORKFLOW_FAILED_MESSAGE = 'Digest generation failed.'

/** Exact assistant content the backend writes when the request itself fails. */
export const REQUEST_FAILED_MESSAGE = 'Request failed.'

/** The failure rows the backend persists, which load back as a danger alert. */
const FAILED_ASSISTANT_MESSAGES = [WORKFLOW_FAILED_MESSAGE, REQUEST_FAILED_MESSAGE]

/** What the composer knows about the question it is sending. */
export interface SentSourcesInput {
  names: string[]
  perSource: number
}

/** The chip row under a question: one chip per source, plus the count chip. */
export interface SentSourcesVm {
  sources: { kind: EntryKind; label: string }[]
  perSource: number | null
}

/**
 * The source chips a question carries. Only messages the user sent during this page
 * session have them, and unknown connector names are dropped rather than labelled.
 */
export function toSentSourcesVm(input: SentSourcesInput): SentSourcesVm {
  const sources: SentSourcesVm['sources'] = []
  for (const name of input.names) {
    const kind = sourceKindOf(name)
    if (kind !== null) {
      sources.push({ kind, label: sourceLabel(kind) })
    }
  }
  return { sources, perSource: input.perSource }
}

/** The chips a saved question carries, from what its digest run actually used. */
export function toResolvedSourcesVm(request: ResolvedRequestOut): SentSourcesVm {
  const sources: SentSourcesVm['sources'] = []
  for (const name of request.sources ?? []) {
    const kind = sourceKindOf(name)
    if (kind !== null) {
      sources.push({ kind, label: sourceLabel(kind) })
    }
  }
  return { sources, perSource: request.per_source ?? null }
}

export type MessageKind = 'user' | 'digest' | 'markdown' | 'cancelled' | 'failed'

export interface MessageVm {
  id: number
  sequence: number
  kind: MessageKind
  text: string
  createdAt: string
  digest?: DigestVm
  /** The alert a persisted failure carries; set only on a `failed` row. */
  alert?: RequestStateVm
  /** The sources a question was sent with, for messages sent in this page session. */
  chips?: SentSourcesVm
  warnings: WarningVm[]
  /** User message: optional follow-up target chip. */
  ref?: RefVm
  followupAction?: FollowupActionVm
  /** Assistant message: link to the preceding user's follow-up target (`re: #n`). */
  replyRef?: RefVm
}

/** Terminal request states the thread shows as an alert rather than a reply. */
export interface RequestStateVm {
  kind: 'failed' | 'interrupted'
  message: string
  canRunAgain: boolean
  /** Offered while the request may still be running, after the polls ran out. */
  canRetryPoll?: boolean
}

const INTERRUPTED_MESSAGE = 'This request was interrupted by a restart'
const FAILED_MESSAGE = 'The request failed.'

export interface RequestStateInput {
  status: string
  error_code?: string | null
  error_message?: string | null
  /** True when the client does not know the outcome yet and can poll again. */
  canRetryPoll?: boolean
}

/**
 * Map a request status to a terminal alert, or null when the status is not one.
 *
 * Only `failed` and `interrupted` produce an alert; `cancelled` is rendered from the
 * cancelled reply message instead.
 */
export function toRequestStateVm(request: RequestStateInput): RequestStateVm | null {
  if (request.status === 'interrupted') {
    return { kind: 'interrupted', message: INTERRUPTED_MESSAGE, canRunAgain: true }
  }
  if (request.status === 'failed') {
    return {
      kind: 'failed',
      message: textOrNull(request.error_message ?? null) ?? FAILED_MESSAGE,
      canRunAgain: true,
      ...(request.canRetryPoll === true ? { canRetryPoll: true } : {}),
    }
  }
  return null
}

/** Session row for the sidebar list. */
export interface SessionVm {
  id: string
  title: string
  isUntitled: boolean
  digestCount: number
  busy: boolean
  updatedAt: string
  timeLabel: string
  groupLabel: string
}

export interface SessionGroupVm {
  label: string
  sessions: SessionVm[]
}

const UNTITLED = 'New conversation'

function parseDate(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/** `20:09` for today, `Sep 21` otherwise, falling back to empty for bad input. */
function timeLabel(date: Date | null, now: Date): string {
  if (date === null) {
    return ''
  }
  if (isSameDay(date, now)) {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** `Today`, then a month name, adding the year when it is not the current year. */
function groupLabel(date: Date | null, now: Date): string {
  if (date === null) {
    return ''
  }
  if (isSameDay(date, now)) {
    return 'Today'
  }
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString('en-US', {
    month: 'long',
    ...(sameYear ? {} : { year: 'numeric' }),
  })
}

/** Project one session, naming untitled ones and deriving its list labels. */
export function toSessionVm(session: SessionOut, now: Date): SessionVm {
  const title = textOrNull(session.title)
  const parsed = parseDate(session.updated_at)
  return {
    id: session.id,
    title: title ?? UNTITLED,
    isUntitled: title === null,
    digestCount: session.digest_count ?? 0,
    busy: textOrNull(session.active_request_id ?? null) !== null,
    updatedAt: session.updated_at,
    timeLabel: timeLabel(parsed, now),
    groupLabel: groupLabel(parsed, now),
  }
}

/**
 * Group sessions by recency label, preserving the incoming order inside a group.
 *
 * The API returns sessions newest first, so groups appear in first-seen order.
 */
export function groupSessions(sessions: SessionOut[], now: Date): SessionGroupVm[] {
  const groups: SessionGroupVm[] = []
  for (const session of sessions) {
    const vm = toSessionVm(session, now)
    const current = groups.at(-1)
    if (current !== undefined && current.label === vm.groupLabel) {
      current.sessions.push(vm)
      continue
    }
    groups.push({ label: vm.groupLabel, sessions: [vm] })
  }
  return groups
}

/** Map `(digest_id, display_rank)` → entry title from digest messages in the transcript. */
function buildDigestEntryTitleIndex(messages: MessageOut[]): Map<string, string> {
  const index = new Map<string, string>()
  for (const message of messages) {
    if (message.role !== 'assistant' || message.digest === undefined || message.digest === null) {
      continue
    }
    const digestId = message.digest_id
    if (digestId === undefined || digestId === null) {
      continue
    }
    for (const entry of message.digest.entries ?? []) {
      const title = textOrNull(entry.title ?? null)
      const key = `${digestId}:${entry.display_rank}`
      index.set(key, title !== null && title !== '' ? title : `#${entry.display_rank}`)
    }
  }
  return index
}

function followupTargetToRef(
  target: FollowupTarget,
  digestTitles: Map<string, string>,
): RefVm {
  const key = `${target.digest_id}:${target.display_rank}`
  const title = digestTitles.get(key) ?? `#${target.display_rank}`
  return {
    digestId: target.digest_id,
    rank: target.display_rank,
    title,
  }
}

export interface MessageMapContext {
  digestTitles: Map<string, string>
  /** The immediately preceding user message's follow-up ref, for assistant `re:`. */
  previousUserRef: RefVm | null
}

/**
 * Classify one transcript message. Prefer `toMessages` for full transcripts so entry
 * titles and assistant `re:` links resolve from digest rows.
 */
export function toMessageVm(message: MessageOut, context?: MessageMapContext): MessageVm {
  const warnings = message.warnings ?? []
  const titles = context?.digestTitles ?? new Map<string, string>()
  const vm: MessageVm = {
    id: message.id,
    sequence: message.sequence,
    kind: 'markdown',
    text: message.content,
    createdAt: message.created_at,
    warnings: warnings.map(toWarningVm),
  }
  if (message.role === 'user') {
    vm.kind = 'user'
    if (message.request) {
      vm.chips = toResolvedSourcesVm(message.request)
    }
    if (message.followup_target !== undefined && message.followup_target !== null) {
      vm.ref = followupTargetToRef(message.followup_target, titles)
      const action = message.followup_action
      if (action === 'deep_dive' || action === 'ask') {
        vm.followupAction = action
      }
    }
    return vm
  }
  if (message.digest !== null && message.digest !== undefined) {
    vm.kind = 'digest'
    vm.digest = toDigestVm({
      digest: message.digest,
      digestId: message.digest_id ?? null,
      warnings,
    })
    vm.warnings = vm.digest.warnings
    if (context?.previousUserRef !== undefined && context?.previousUserRef !== null) {
      vm.replyRef = context.previousUserRef
    }
    return vm
  }
  if (message.content === CANCELLED_ASSISTANT_MESSAGE) {
    vm.kind = 'cancelled'
    return vm
  }
  if (FAILED_ASSISTANT_MESSAGES.includes(message.content.trim())) {
    vm.kind = 'failed'
    vm.alert = { kind: 'failed', message: vm.text, canRunAgain: true }
    return vm
  }
  if (context?.previousUserRef !== undefined && context?.previousUserRef !== null) {
    vm.replyRef = context.previousUserRef
  }
  return vm
}

/** Sort and map a page of API messages; resolves follow-up titles from digest rows. */
export function toMessages(loaded: MessageOut[]): MessageVm[] {
  const sorted = [...loaded].sort((a, b) => a.sequence - b.sequence)
  const digestTitles = buildDigestEntryTitleIndex(sorted)
  let previousUserRef: RefVm | null = null
  const out: MessageVm[] = []
  for (const message of sorted) {
    const vm = toMessageVm(message, { digestTitles, previousUserRef })
    out.push(vm)
    if (message.role === 'user') {
      previousUserRef = vm.ref ?? null
    }
  }
  return out
}
