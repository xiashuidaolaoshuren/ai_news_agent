import type { ConnectorWarning, DigestView, JuyaDigestEntryView, SourceKind } from '@/api/generated/types.gen'
import type { ApiDigestEntry } from '@/vm/entries'
import { resolveDemoAsset, safeHttpUrl, textOrNull, toVm } from '@/vm/entries'
import type { EntryKind, EntryVm } from '@/vm/types'

export type SectionSubtitle = string | null

/** One Juya issue with its stories, collapsed into a single cover block. */
export interface JuyaIssueVm {
  issueId: string
  eyebrow: string
  coverUrl: string | null
  coverAlt: string | null
  leadTitle: string | null
  issueUrl: string | null
  stories: EntryVm[]
}

export interface SectionVm {
  kind: EntryKind
  label: string
  subtitle: SectionSubtitle
  count: number
  rangeStart: number
  rangeEnd: number
  entries: EntryVm[]
  juyaIssues?: JuyaIssueVm[]
}

const SOURCE_LABELS: Record<EntryKind, string> = {
  juya: 'Juya',
  huggingface: 'Hugging Face',
  github: 'GitHub',
  zhihu: 'Zhihu',
  bilibili: 'Bilibili',
}

const SECTION_SUBTITLES: Partial<Record<EntryKind, string>> = {
  juya: '橘鸦 AI 早报',
  huggingface: 'Trending models',
  github: 'Trending repositories',
}

/** Display label for a source kind. */
export function sourceLabel(kind: SourceKind): string {
  return SOURCE_LABELS[kind]
}

function juyaEyebrow(date: string | null | undefined): string {
  const day = textOrNull(date ?? null)
  return day === null ? 'AI 早报' : `AI 早报 · ${day}`
}

/**
 * Group a Juya section's entries by `issue.id`.
 *
 * The cover comes from the first entry in the group that has one. Entries without
 * an issue id share a single coverless group. No issue number is ever produced.
 */
export function toJuyaIssuesVm(
  apis: JuyaDigestEntryView[],
  vms: EntryVm[],
): JuyaIssueVm[] {
  const groups = new Map<string, JuyaIssueVm>()
  apis.forEach((api, index) => {
    const vm = vms[index]
    if (vm === undefined) {
      return
    }
    const issueId = textOrNull(api.issue?.id ?? null) ?? ''
    let group = groups.get(issueId)
    if (group === undefined) {
      group = {
        issueId,
        eyebrow: juyaEyebrow(api.issue?.date),
        coverUrl: resolveDemoAsset(api.issue?.cover_url),
        coverAlt: textOrNull(api.issue?.lead_title ?? null),
        leadTitle: textOrNull(api.issue?.lead_title ?? null),
        issueUrl: safeHttpUrl(api.issue?.url),
        stories: [],
      }
      groups.set(issueId, group)
    } else if (group.coverUrl === null) {
      group.coverUrl = resolveDemoAsset(api.issue?.cover_url)
    }
    group.stories.push(vm)
  })
  return [...groups.values()]
}

/** Entry with its Juya story presentation attached. */
function toJuyaEntryVm(api: JuyaDigestEntryView): EntryVm {
  const vm = toVm(api)
  vm.juya = {
    topic: textOrNull(api.story?.section ?? null),
    originalUrl: safeHttpUrl(api.story?.original_url),
  }
  return vm
}

/**
 * Group entries into contiguous `source_kind` runs, preserving entry order.
 *
 * Interleaved kinds produce several sections of the same kind; the rank range is
 * the first and last `display_rank` in the run, so ranges stay continuous.
 */
export function toSectionsVm(entries: ApiDigestEntry[]): SectionVm[] {
  const sections: SectionVm[] = []
  const sectionApis: ApiDigestEntry[][] = []
  for (const api of entries) {
    const vm: EntryVm = api.source_kind === 'juya' ? toJuyaEntryVm(api) : toVm(api)
    const current = sections.at(-1)
    if (current !== undefined && current.kind === vm.kind) {
      current.entries.push(vm)
      current.count += 1
      current.rangeEnd = vm.rank
      sectionApis.at(-1)?.push(api)
      continue
    }
    sections.push({
      kind: vm.kind,
      label: SOURCE_LABELS[vm.kind],
      subtitle: SECTION_SUBTITLES[vm.kind] ?? null,
      count: 1,
      rangeStart: vm.rank,
      rangeEnd: vm.rank,
      entries: [vm],
    })
    sectionApis.push([api])
  }
  sections.forEach((section, index) => {
    if (section.kind !== 'juya') {
      return
    }
    const apis = (sectionApis[index] ?? []).filter(
      (api): api is JuyaDigestEntryView => api.source_kind === 'juya',
    )
    section.juyaIssues = toJuyaIssuesVm(apis, section.entries)
  })
  return sections
}

/** Connector warning ready for an `alert-warn` block. */
export interface WarningVm {
  source: string
  label: string
  code: string
  message: string
}

export interface DigestVm {
  ref: string | null
  generatedAt: string
  itemCount: number
  sourcesReturned: number
  sourcesTotal: number
  warnings: WarningVm[]
  sections: SectionVm[]
}

export interface DigestVmInput {
  digest: DigestView
  digestId?: number | null
  warnings?: ConnectorWarning[]
  connectorNames?: string[] | null
}

/** Connector warning with a display label; unknown connectors keep their raw name. */
export function toWarningVm(warning: ConnectorWarning): WarningVm {
  const known = (SOURCE_LABELS as Record<string, string | undefined>)[warning.connector]
  return {
    source: warning.connector,
    label: known ?? warning.connector,
    code: warning.code,
    message: warning.message,
  }
}

function sourceNames(warning: ConnectorWarning): EntryKind | null {
  return warning.connector in SOURCE_LABELS ? (warning.connector as EntryKind) : null
}

/** Project a digest and its connector warnings onto the digest-reply view-model. */
export function toDigestVm(input: DigestVmInput): DigestVm {
  const entries = (input.digest.entries ?? []) as ApiDigestEntry[]
  const sections = toSectionsVm(entries)
  const warnings = (input.warnings ?? []).map(toWarningVm)
  const seen = new Set<EntryKind>()
  for (const kind of input.connectorNames ?? []) {
    if (kind in SOURCE_LABELS) {
      seen.add(kind as EntryKind)
    }
  }
  for (const section of sections) {
    seen.add(section.kind)
  }
  for (const warning of input.warnings ?? []) {
    const kind = sourceNames(warning)
    if (kind !== null) {
      seen.add(kind)
    }
  }
  const returned = new Set<EntryKind>(sections.map((section) => section.kind))
  return {
    ref: typeof input.digestId === 'number' ? `d${input.digestId}` : null,
    generatedAt: input.digest.generated_at,
    itemCount: entries.length,
    sourcesReturned: returned.size,
    sourcesTotal: seen.size,
    warnings,
    sections,
  }
}
