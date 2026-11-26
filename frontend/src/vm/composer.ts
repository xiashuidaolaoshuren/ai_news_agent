import { sourceLabel } from '@/vm/digest'
import { sourceKind } from '@/vm/run'
import type { EntryKind, RefVm } from '@/vm/types'

/** Credential health for the current credential version, as `GET /sources` reports it. */
export type SourceHealth =
  | 'ok'
  | 'auth_error'
  | 'unavailable'
  | 'rate_limited'
  | 'timeout'
  | 'stale'
  | 'unchecked'

/** One connector the composer can select, as `GET /sources` describes it. */
export interface SourceOption {
  name: string
  label: string
  kind: EntryKind | null
  default: boolean
  health: SourceHealth
}

/** The tooltip a chip shows; ok and unchecked carry no warning. */
export function healthHint(health: SourceHealth): string | null {
  switch (health) {
    case 'auth_error':
      return 'Last check: authentication error.'
    case 'stale':
      return 'Not checked since update.'
    case 'unavailable':
      return 'Last check: source unavailable.'
    case 'rate_limited':
      return 'Last check: rate limited.'
    case 'timeout':
      return 'Last check: timed out.'
    default:
      return null
  }
}

function readHealth(value: unknown): SourceHealth {
  if (!isRecord(value)) {
    return 'unchecked'
  }
  if (typeof value.current === 'string') {
    return value.current as SourceHealth
  }
  return value.stale === true ? 'stale' : 'unchecked'
}

/** One source checkbox row. */
export interface ComposerSourceVm extends SourceOption {
  checked: boolean
  /** Tooltip for a source whose credential health is not ok. */
  healthHint: string | null
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
      health: readHealth(item.health),
    })
  }
  return options
}

/**
 * The names hidden from discovery, as `GET /sources` reports them alongside the
 * visible catalog. Unknown shapes hide nothing.
 */
export function parseHiddenSources(raw: unknown): string[] {
  if (!isRecord(raw) || !Array.isArray(raw.hidden)) {
    return []
  }
  return raw.hidden.filter((name): name is string => typeof name === 'string' && name !== '')
}

/** The preferences the composer edits, as raw UI state. */
export interface ComposerPrefs {
  selected: string[]
}

/** The subset of `SessionOut` the composer preferences come from. */
export interface PrefsSession {
  connector_names: string[] | null
}

function visibleDefaults(sources: SourceOption[]): string[] {
  return sources.filter((item) => item.default).map((item) => item.name)
}

/**
 * Preferences to show for one session. Until the first PATCH the session stores
 * nothing, so the catalog defaults stand in.
 *
 * A stored name the catalog hides is dropped from the display only; the caller
 * never writes that drop back. When nothing visible remains, the defaults stand in.
 */
export function prefsFor(
  session: PrefsSession | null,
  sources: SourceOption[],
  hidden: string[],
): ComposerPrefs {
  const stored = session?.connector_names ?? null
  if (stored === null) {
    return { selected: visibleDefaults(sources) }
  }
  const visible = stored.filter((name) => !hidden.includes(name))
  return { selected: visible.length === 0 ? visibleDefaults(sources) : visible }
}

/** Error copy, aligned with the backend's 400s so the client can check first. */
export const TEXT_REQUIRED = 'Type a question or topic first.'
export const SOURCE_REQUIRED = 'Select at least one source.'

/** Shown when the send call itself fails, or when a preference PATCH is refused. */
export const SEND_FAILED = 'Could not send this message.'
export const PREFS_FAILED = 'Could not update this conversation’s sources.'
export const FOLLOWUP_TARGET_UNAVAILABLE = 'That entry is no longer available.'
export const REPEAT_UNAVAILABLE = 'That request can’t be repeated.'

/** One message per failing rule, keyed by the field that owns it. */
export interface ComposerErrors {
  text?: string
  sources?: string
  send?: string
  prefs?: string
}

/** The fields the send rules read. */
export interface ComposerDraft {
  text: string
  selected: string[]
}

/** Reject a draft the backend would answer with a 400. */
export function validateComposer(draft: ComposerDraft): ComposerErrors {
  const errors: ComposerErrors = {}
  if (draft.text.trim() === '') {
    errors.text = TEXT_REQUIRED
  }
  if (draft.selected.length === 0) {
    errors.sources = SOURCE_REQUIRED
  }
  return errors
}

/** Which of the composer's notices the dock shows above the textarea. */
export type ComposerNotice = 'none' | 'running' | 'reconnecting' | 'blocked'

export interface ComposerVmInput {
  text: string
  sources: SourceOption[]
  selected: string[]
  errors: ComposerErrors
  busy: boolean
  notice: ComposerNotice
  /** Optional follow-up target; drives placeholder and chip. */
  ref: RefVm | null
  countsSeen: boolean
  /** The transcript failed to load, so the prototype refuses a send. */
  loadFailed?: boolean
  /** A send was refused because a Juya confirmation is still unanswered. */
  confirmPending?: boolean
  /** The note shown after the user cancels a Juya confirmation. */
  confirmCancelled?: string | null
}

/** Everything the composer renders; the component reads no other state. */
export interface ComposerVm {
  text: string
  sources: ComposerSourceVm[]
  busy: boolean
  notice: ComposerNotice
  errors: ComposerErrors
  ref: RefVm | null
  placeholder: string
  countsSeen: boolean
  loadFailed: boolean
  confirmPending: boolean
  confirmCancelled: string | null
}

function placeholderFor(ref: RefVm | null): string {
  if (ref === null) {
    return 'Ask for a digest or a follow-up…'
  }
  return `Ask about d${ref.digestId} #${ref.rank}…`
}

/** Bind the composer's raw state to one render-ready view-model. */
export function toComposerVm(input: ComposerVmInput): ComposerVm {
  return {
    text: input.text,
    sources: input.sources.map((source) => ({
      ...source,
      checked: input.selected.includes(source.name),
      healthHint: healthHint(source.health),
    })),
    busy: input.busy,
    notice: input.notice,
    errors: input.errors,
    ref: input.ref,
    placeholder: placeholderFor(input.ref),
    countsSeen: input.countsSeen,
    loadFailed: input.loadFailed === true,
    confirmPending: input.confirmPending === true,
    confirmCancelled: input.confirmCancelled ?? null,
  }
}
