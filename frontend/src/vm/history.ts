import type {
  HistoryItemShowOut,
  HistorySearchMatchOut,
  HistorySearchResultOut,
  SearchHistoryApiV1HistorySearchGetData,
  SessionSearchHitOut,
} from '@/api/generated/types.gen'
import { sourceLabel } from '@/vm/digest'
import { hostOf, safeHttpUrl, textOrNull, toEntryVm } from '@/vm/entries'
import type { EntryKind, EntryVm } from '@/vm/types'

/** Session search result row. */
export interface SessionHitVm {
  sessionId: string
  title: string
  matchKind: 'title' | 'user' | 'assistant'
  excerpt: string | null
  updatedAt: string
}

/** One history search result row. */
export interface HistoryMatchVm {
  token: string
  digestId: number
  rank: number
  dateLabel: string
  sourceKind: EntryKind
  label: string
  title: string
  url: string | null
  host: string | null
  excerpt: string | null
  topics: string[]
}

const UNTITLED = 'New conversation'

/** Project one session search hit, naming untitled sessions. */
export function toSessionHitVm(hit: SessionSearchHitOut): SessionHitVm {
  return {
    sessionId: hit.session_id,
    title: textOrNull(hit.title) ?? UNTITLED,
    matchKind: hit.match_kind,
    excerpt: textOrNull(hit.excerpt),
    updatedAt: hit.updated_at,
  }
}

/** Calendar day of a timestamp, taken from the string so no timezone shifts it. */
function dateLabel(generatedAt: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(generatedAt)
  return match?.[1] ?? generatedAt
}

/** Project one history search match for the results list. */
export function toHistoryMatchVm(match: HistorySearchMatchOut): HistoryMatchVm {
  const url = safeHttpUrl(match.url)
  const kind = match.source_kind as EntryKind
  return {
    token: match.ref.token,
    digestId: match.ref.digest_id,
    rank: match.ref.rank,
    dateLabel: dateLabel(match.generated_at),
    sourceKind: kind,
    label: sourceLabel(kind),
    title: match.title,
    url,
    host: hostOf(url),
    excerpt: textOrNull(match.excerpt ?? null),
    topics: match.topics ?? [],
  }
}

/**
 * The filter draft in the history panel. Source `all` means "no source filter".
 */
export interface HistoryFilters {
  text: string
  source: string
  topic: string
  from: string
  to: string
}

/** Nothing entered yet, which makes the panel show its idle prompt. */
export const EMPTY_HISTORY_FILTERS: HistoryFilters = {
  text: '',
  source: 'all',
  topic: '',
  from: '',
  to: '',
}

/** How many matches the API returns per search. */
export const HISTORY_LIMIT = 10

/** The search query the panel sends, with every field already normalized. */
export type HistorySearchQuery = NonNullable<SearchHistoryApiV1HistorySearchGetData['query']>

/** Source kinds in the panel's order, behind the all-sources option. */
const HISTORY_SOURCES: EntryKind[] = ['juya', 'huggingface', 'github', 'zhihu', 'bilibili']

/** The prototype's short source value, mapped onto the API's name. */
const SOURCE_ALIASES: Record<string, string> = { hf: 'huggingface' }

/** The source `<select>` options: all sources, then one row per kind. */
export function historySourceOptions(): { value: string; label: string }[] {
  return [
    { value: 'all', label: 'All sources' },
    ...HISTORY_SOURCES.map((kind) => ({ value: kind, label: sourceLabel(kind) })),
  ]
}

/**
 * The API source name for a panel value, or null when no source is selected.
 * Prototype values (`hf`) and any casing are accepted.
 */
function normalizeSource(value: string): string | null {
  const key = value.trim().toLowerCase()
  if (key === '' || key === 'all') {
    return null
  }
  return SOURCE_ALIASES[key] ?? key
}

/** The topic input is free text; commas separate several topics. */
function splitTopics(value: string): string | null {
  const parts = value
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part !== '')
  return parts.length === 0 ? null : parts.join(',')
}

/** Trimmed value, or null when the field is blank. */
function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/**
 * The search query for the current filters, or null when no criterion is set.
 * The API rejects an empty query, so the panel makes no call in that case.
 */
export function toHistoryQuery(filters: HistoryFilters): HistorySearchQuery | null {
  const query: HistorySearchQuery = {
    limit: HISTORY_LIMIT,
  }
  const text = trimmedOrNull(filters.text)
  const source = normalizeSource(filters.source)
  const topics = splitTopics(filters.topic)
  const since = trimmedOrNull(filters.from)
  const until = trimmedOrNull(filters.to)
  let active = false
  if (text !== null) {
    query.text = text
    active = true
  }
  if (source !== null) {
    query.sources = source
    active = true
  }
  if (topics !== null) {
    query.topics = topics
    active = true
  }
  if (since !== null) {
    query.since = since
    active = true
  }
  if (until !== null) {
    query.until = until
    active = true
  }
  return active ? query : null
}

/** How many filters the count line reports, using the same rule as the query. */
export function filterCount(filters: HistoryFilters): number {
  return [
    trimmedOrNull(filters.text) !== null,
    normalizeSource(filters.source) !== null,
    splitTopics(filters.topic) !== null,
    trimmedOrNull(filters.from) !== null,
    trimmedOrNull(filters.to) !== null,
  ].filter(Boolean).length
}

/** The backend's own truncation caveat, so the panel never repeats it. */
const TRUNCATION_CAVEAT =
  'The search scanned only the newest matching entries; older archive rows were not searched.'

/** The backend's no-match caveat, which the empty state already says in full. */
const NO_MATCH_PREFIX = 'No historical digest entries matched'

/** One search response, ready for the results list and the count bar. */
export interface HistoryResultVm {
  matches: HistoryMatchVm[]
  countLabel: string
  notes: string[]
  empty: boolean
}

/**
 * Project one search response: the rows, the "N results · M filters" count, and
 * the caveats under it. A no-match caveat is dropped while the list is empty,
 * because the empty state carries that message.
 */
export function toHistoryResultVm(
  out: HistorySearchResultOut,
  activeFilters: number,
): HistoryResultVm {
  const matches = out.matches.map(toHistoryMatchVm)
  const empty = matches.length === 0
  const notes = (out.caveats ?? []).filter(
    (caveat) => !(empty && caveat.startsWith(NO_MATCH_PREFIX)),
  )
  if (out.archive_truncated && !notes.some((note) => /truncat|older archive/i.test(note))) {
    notes.push(TRUNCATION_CAVEAT)
  }
  const count = `${matches.length} result${matches.length === 1 ? '' : 's'}`
  const filters =
    activeFilters === 0
      ? ''
      : ` · ${activeFilters} filter${activeFilters === 1 ? '' : 's'}`
  return { matches, countLabel: `${count}${filters}`, notes, empty }
}

/** One opened historical item: the entry when the API resolved it, else markdown. */
export interface OpenedItemVm {
  token: string
  entry: EntryVm | null
  markdown: string
}

/**
 * Project `GET /history/{token}`. The entry goes through the shared entry mapper,
 * so the opened result looks like any other digest entry; `markdown` is the
 * fallback the panel renders when the entry could not be resolved.
 */
export function toOpenedVm(show: HistoryItemShowOut): OpenedItemVm {
  return {
    token: show.token,
    entry: show.entry == null ? null : toEntryVm(show.entry),
    markdown: show.markdown,
  }
}

/** What the panel is showing right now. */
export type HistoryState = 'idle' | 'loading' | 'results' | 'empty' | 'error'

/** Where the current search stands, before it becomes a panel state. */
export type HistoryStatus = 'idle' | 'loading' | 'ready' | 'error'

/** The idle prompt: the API needs a criterion, so the panel asks for one. */
const IDLE_TITLE = 'Search past digests'
const IDLE_BODY = 'Enter text, a source, a topic or a date range.'

/** The no-match state, in the prototype's shape: name what was searched for. */
const NO_MATCH_TITLE = 'No matches'

/** "Nothing in past digests matches X from Y in Z. Try a broader term or remove a filter." */
export function noMatchBody(filters: HistoryFilters): string {
  let tail = ''
  const text = trimmedOrNull(filters.text)
  const source = normalizeSource(filters.source)
  const topics = splitTopics(filters.topic)
  if (text !== null) {
    tail += ` \u201c${text}\u201d`
  }
  if (source !== null) {
    tail += ` from ${sourceLabel(source as EntryKind)}`
  }
  if (topics !== null) {
    tail += ` in ${topics.split(',').join(', ')}`
  }
  if (trimmedOrNull(filters.from) !== null || trimmedOrNull(filters.to) !== null) {
    tail += ' in the selected date range'
  }
  return `Nothing in past digests matches${tail}. Try a broader term or remove a filter.`
}

/** Everything the panel renders, derived from the filter draft and the response. */
export interface HistoryPanelVm {
  filters: HistoryFilters
  sourceOptions: { value: string; label: string }[]
  state: HistoryState
  countLabel: string
  notes: string[]
  matches: HistoryMatchVm[]
  emptyTitle: string
  emptyBody: string
  /** The failing message the panel shows inline, or null. */
  error: string | null
  /** The result the user opened, shown above the list. */
  opened: OpenedResultVm | null
}

/** The opened result: the row it came from, plus the item the API returned. */
export interface OpenedResultVm {
  match: HistoryMatchVm
  item: OpenedItemVm | null
  loading: boolean
  error: string | null
}

/** The store state behind an opened result. */
export interface OpenedResultInput {
  match: HistoryMatchVm
  status: HistoryStatus
  item: OpenedItemVm | null
  error: string | null
}

/** The store state the panel view-model is built from. */
export interface HistoryPanelInput {
  filters: HistoryFilters
  status: HistoryStatus
  result: HistorySearchResultOut | null
  error: string | null
  opened: OpenedResultInput | null
}

/**
 * Build the panel view-model. With no criterion the panel stays idle and shows
 * the prompt; the API requires at least one criterion, so it is never called.
 */
export function toHistoryPanelVm(input: HistoryPanelInput): HistoryPanelVm {
  const idle = toHistoryQuery(input.filters) === null
  const result =
    input.result === null ? null : toHistoryResultVm(input.result, filterCount(input.filters))
  let state: HistoryState
  if (idle) {
    state = 'idle'
  } else if (input.status === 'loading') {
    state = 'loading'
  } else if (input.status === 'error') {
    state = 'error'
  } else if (result === null) {
    state = 'loading'
  } else {
    state = result.empty ? 'empty' : 'results'
  }
  return {
    filters: input.filters,
    sourceOptions: historySourceOptions(),
    state,
    countLabel: result?.countLabel ?? '',
    notes: result?.notes ?? [],
    matches: result?.matches ?? [],
    emptyTitle: idle ? IDLE_TITLE : NO_MATCH_TITLE,
    emptyBody: idle ? IDLE_BODY : noMatchBody(input.filters),
    error: input.error,
    opened: input.opened === null ? null : toOpenedResultVm(input.opened),
  }
}

/** Project the opened result: a loading flag while the show call is in flight. */
export function toOpenedResultVm(input: OpenedResultInput): OpenedResultVm {
  return {
    match: input.match,
    item: input.item,
    loading: input.status === 'loading',
    error: input.error,
  }
}
