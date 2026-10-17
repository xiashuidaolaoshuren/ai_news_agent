import { sourceLabel } from '@/vm/digest'
import { sourceKind } from '@/vm/run'
import type { EntryKind } from '@/vm/types'

/** Stepper bounds from the spec (1-20), not the prototype's narrower demo range. */
export const COUNT_MIN = 1
export const COUNT_MAX = 20

/** Count shown before the session carries its own preference. */
export const DEFAULT_ITEMS_PER_SOURCE = 5

/** One connector the composer can select, as `GET /sources` describes it. */
export interface SourceOption {
  name: string
  label: string
  kind: EntryKind | null
  default: boolean
}

/** One source checkbox row. */
export interface ComposerSourceVm extends SourceOption {
  checked: boolean
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Read the connector catalog out of `GET /sources`, which the generated client
 * types as `unknown`. An unknown connector keeps its raw name and shows no logo.
 */
export function parseSources(raw: unknown): SourceOption[] {
  if (!isRecord(raw) || !Array.isArray(raw.sources)) {
    return []
  }
  const options: SourceOption[] = []
  for (const item of raw.sources) {
    if (!isRecord(item) || typeof item.name !== 'string') {
      continue
    }
    const kind = sourceKind(item.name)
    options.push({
      name: item.name,
      label: kind === null ? item.name : sourceLabel(kind),
      kind,
      default: item.default === true,
    })
  }
  return options
}

/** The preferences the composer edits, as raw UI state. */
export interface ComposerPrefs {
  selected: string[]
  count: string
}

/** The subset of `SessionOut` the composer preferences come from. */
export interface PrefsSession {
  connector_names: string[] | null
  items_per_source: number | null
}

/**
 * Preferences to show for one session. Until the first PATCH the session stores
 * nothing, so the catalog defaults and a count of 5 stand in.
 */
export function prefsFor(
  session: PrefsSession | null,
  sources: SourceOption[],
): ComposerPrefs {
  return {
    selected:
      session?.connector_names ?? sources.filter((item) => item.default).map((item) => item.name),
    count: String(session?.items_per_source ?? DEFAULT_ITEMS_PER_SOURCE),
  }
}

/** Error copy, aligned with the backend's 400s so the client can check first. */
export const TEXT_REQUIRED = 'Type a question or topic first.'
export const SOURCE_REQUIRED = 'Select at least one source.'
export const COUNT_INVALID = `Items per source must be a whole number from ${COUNT_MIN} to ${COUNT_MAX}.`

/** Shown when the send call itself fails, or when a preference PATCH is refused. */
export const SEND_FAILED = 'Could not send this message.'
export const PREFS_FAILED = 'Could not update this conversation’s sources.'

/** One message per failing rule, keyed by the field that owns it. */
export interface ComposerErrors {
  text?: string
  sources?: string
  count?: string
  send?: string
  prefs?: string
}

/** The fields the send rules read. */
export interface ComposerDraft {
  text: string
  selected: string[]
  count: string
}

/** Reject a draft the backend would answer with a 400. */
export function validateComposer(draft: ComposerDraft): ComposerErrors {
  const errors: ComposerErrors = {}
  const count = Number(draft.count)
  if (draft.text.trim() === '') {
    errors.text = TEXT_REQUIRED
  }
  if (draft.selected.length === 0) {
    errors.sources = SOURCE_REQUIRED
  }
  if (!Number.isInteger(count) || count < COUNT_MIN || count > COUNT_MAX) {
    errors.count = COUNT_INVALID
  }
  return errors
}

/** Which of the composer's notices the dock shows above the textarea. */
export type ComposerNotice = 'none' | 'running' | 'reconnecting' | 'blocked'

export interface ComposerVmInput {
  text: string
  sources: SourceOption[]
  selected: string[]
  count: string
  errors: ComposerErrors
  busy: boolean
  notice: ComposerNotice
}

/** Everything the composer renders; the component reads no other state. */
export interface ComposerVm {
  text: string
  sources: ComposerSourceVm[]
  count: string
  busy: boolean
  notice: ComposerNotice
  errors: ComposerErrors
}

/** Bind the composer's raw state to one render-ready view-model. */
export function toComposerVm(input: ComposerVmInput): ComposerVm {
  return {
    text: input.text,
    sources: input.sources.map((source) => ({
      ...source,
      checked: input.selected.includes(source.name),
    })),
    count: input.count,
    busy: input.busy,
    notice: input.notice,
    errors: input.errors,
  }
}
