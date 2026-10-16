import type { LifecycleState } from '@/api/lifecycle'
import { sourceLabel } from '@/vm/digest'
import type { EntryKind } from '@/vm/types'

/** Step marker for one source in the run card's list and segmented bar. */
export type StepStatus = 'queued' | 'run' | 'done' | 'warn'

export interface RunStepVm {
  source: string | null
  kind: EntryKind | null
  label: string
  status: StepStatus
  count: number | null
  at: string | null
}

/** One `progress` event plus the local clock label for when it arrived. */
export interface RunProgress {
  stage: string
  source: string | null
  status: 'running' | 'done' | 'failed' | null
  count: number | null
  at?: string | null
}

export interface RunVmInput {
  state: LifecycleState
  progress: RunProgress[]
  text: string
  attempt: number
  nextDelayMs: number | null
  selectedSources: string[] | null
  startedAt: string | null
  droppedAt: string | null
  endedAt: string | null
  reconnected: boolean
  /** True once the reconnected banner is collapsing out, just before it clears. */
  reconnectLeaving: boolean
  /** The stream ended but the reply's paced reveal is still catching up. */
  holding: boolean
}

export interface ReconnectVm {
  droppedAt: string | null
  attempt: number
  max: number
  nextSeconds: number | null
  ok: boolean
}

/** Cancelled reply copy inputs; counts stay null when the run never reported sources. */
export interface CancelledVm {
  mode: 'digest' | 'text'
  at: string | null
  done: number | null
  total: number | null
}

export interface RunVm {
  mode: 'digest' | 'followup'
  phase: 'fetching' | 'writing'
  headline: string
  steps: RunStepVm[]
  finished: number
  total: number
  startedAt: string | null
  structured: boolean
  fallbackStage: string | null
  streamText: string
  /** The stream has stopped, so the reply's reveal should drain and then finish. */
  ended: boolean
  reconnect: ReconnectVm | null
  /** The reconnected banner is on its way out; it collapses as it goes. */
  reconnectLeaving: boolean
}

const KINDS: Record<string, EntryKind> = {
  juya: 'juya',
  huggingface: 'huggingface',
  github: 'github',
  zhihu: 'zhihu',
  bilibili: 'bilibili',
}

/** Entry kind for a connector name, or null when the stream sends an unknown one. */
export function sourceKind(source: string | null): EntryKind | null {
  return source === null ? null : (KINDS[source] ?? null)
}

/** Display label for a connector name, falling back to the raw name. */
function labelFor(source: string | null): string {
  if (source === null) {
    return ''
  }
  const kind = sourceKind(source)
  return kind === null ? source : sourceLabel(kind)
}

/** Seed one queued step per selected source, in the order the API returns them. */
function seed(source: string | null): RunStepVm {
  return {
    source,
    kind: sourceKind(source),
    label: labelFor(source),
    status: 'queued',
    count: null,
    at: null,
  }
}

/** Build the step list from the selected sources plus every progress event. */
function buildSteps(input: RunVmInput): RunStepVm[] {
  const steps = (input.selectedSources ?? []).map((source) => seed(source))
  for (const event of input.progress) {
    if (event.source === null) {
      continue
    }
    let index = steps.findIndex((step) => step.source === event.source)
    if (index === -1) {
      steps.push(seed(event.source))
      index = steps.length - 1
    }
    const step = steps[index]
    if (step === undefined) {
      continue
    }
    if (event.status === 'running') {
      step.status = 'run'
      step.count = null
    } else if (event.status === 'done') {
      step.status = 'done'
      step.count = event.count
      step.at = event.at ?? null
    } else if (event.status === 'failed') {
      step.status = 'warn'
      step.count = null
      step.at = event.at ?? null
    }
  }
  return steps
}

const MAX_ATTEMPTS = 5

/** Digest mode when connector progress arrived, text mode when only reply text did. */
function runMode(input: RunVmInput, structured: boolean): 'digest' | 'followup' {
  return !structured && input.text !== '' ? 'followup' : 'digest'
}

/** Counts and clock label for the cancelled reply; null when no run was cancelled. */
export function toCancelledVm(input: RunVmInput): CancelledVm | null {
  if (input.state !== 'cancelled') {
    return null
  }
  const structured = input.progress.some((event) => event.source !== null)
  const mode = runMode(input, structured)
  const steps = buildSteps(input)
  const digest = mode === 'digest' && steps.length > 0
  return {
    mode: mode === 'followup' ? 'text' : 'digest',
    at: input.endedAt,
    done: digest
      ? steps.filter((step) => step.status === 'done' || step.status === 'warn').length
      : null,
    total: digest ? steps.length : null,
  }
}

function reconnectVm(input: RunVmInput): ReconnectVm | null {
  if (input.state === 'reconnecting') {
    return {
      droppedAt: input.droppedAt,
      attempt: input.attempt,
      max: MAX_ATTEMPTS,
      nextSeconds: input.nextDelayMs === null ? null : Math.round(input.nextDelayMs / 1000),
      ok: false,
    }
  }
  if (input.reconnected) {
    return {
      droppedAt: input.droppedAt,
      attempt: input.attempt,
      max: MAX_ATTEMPTS,
      nextSeconds: null,
      ok: true,
    }
  }
  return null
}

/** The card mounts while a run has evidence, while reconnecting, or during the dwell. */
function showsCard(input: RunVmInput): boolean {
  if (input.state === 'reconnecting' || input.reconnected || input.holding) {
    return true
  }
  return input.state === 'streaming' && (input.progress.length > 0 || input.text !== '')
}

export function toRunVm(input: RunVmInput): RunVm | null {
  const steps = buildSteps(input)
  const finished = steps.filter((step) => step.status === 'done' || step.status === 'warn').length
  const fallback = [...input.progress].reverse().find((event) => event.source === null)
  const structured = input.progress.some((event) => event.source !== null)
  if (!showsCard(input)) {
    return null
  }
  const phase = steps.length > 0 && finished === steps.length ? 'writing' : 'fetching'
  const mode = runMode(input, structured)
  return {
    mode,
    phase,
    headline:
      phase === 'writing' ? 'Writing digest' : `Researching · ${finished} of ${steps.length} sources`,
    steps,
    finished,
    total: steps.length,
    startedAt: input.startedAt,
    structured,
    fallbackStage: fallback?.stage ?? null,
    streamText: mode === 'followup' ? input.text : '',
    ended: input.state !== 'streaming' && input.state !== 'reconnecting',
    reconnect: reconnectVm(input),
    reconnectLeaving: input.reconnectLeaving,
  }
}
