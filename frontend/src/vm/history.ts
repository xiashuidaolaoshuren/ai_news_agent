import type { HistorySearchMatchOut, SessionSearchHitOut } from '@/api/generated/types.gen'
import { sourceLabel } from '@/vm/digest'
import { hostOf, safeHttpUrl, textOrNull } from '@/vm/entries'
import type { EntryKind } from '@/vm/types'

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
