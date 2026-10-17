/**
 * The prototype's `streamText` pacing, as a controller the reply block drives.
 * The server replays an already-finished answer in 80-character slices, so the
 * word-by-word feel of the prototype has to come from here.
 */

import { prefersReducedMotion } from '@/lib/motion'

/** Characters to skip before looking for the space the reveal advances to. */
const MIN_STEP = 6

/** Extra characters the search may skip, the prototype's `Math.floor(rand * 8)`. */
const STEP_JITTER = 8

const TICK_MS = 70
const TICK_JITTER_MS = 60

/** The prototype's `reduced()` tick: the reply still arrives whole, just at once. */
const REDUCED_TICK_MS = 15

/** Services the controller needs, injected so a test can pin timing and randomness. */
export interface StreamRevealDeps {
  schedule(handler: () => void, ms: number): number
  cancel(handle: number): void
  random(): number
  reducedMotion(): boolean
}

export interface StreamReveal {
  /** How much of the reply's plain text is on screen, as a character count. */
  revealed(): number
  /** True once the reply stopped growing and the reveal caught up with all of it. */
  finished(): boolean
  /** The cumulative plain text the reply has received so far. */
  received(text: string): void
  /** No more text is coming: reveal the rest, then report `finished`. */
  end(): void
  /** Called on every step so the reply block can redraw at the reveal count. */
  watch(listener: () => void): void
  /** Cancel the pending tick and drop the watchers, as the reply block unmounts. */
  stop(): void
}

function defaultStreamRevealDeps(): StreamRevealDeps {
  return {
    schedule: (handler, ms) => window.setTimeout(handler, ms),
    cancel: (handle) => window.clearTimeout(handle),
    random: () => Math.random(),
    reducedMotion: prefersReducedMotion,
  }
}

export function createStreamReveal(
  overrides: Partial<StreamRevealDeps> = {},
): StreamReveal {
  const deps = { ...defaultStreamRevealDeps(), ...overrides }
  const listeners = new Set<() => void>()
  let count = 0
  let text = ''
  let handle: number | null = null
  let ended = false
  let done = false
  let stopped = false

  function notify(): void {
    for (const listener of [...listeners]) {
      listener()
    }
  }

  function tickMs(): number {
    if (deps.reducedMotion()) {
      return REDUCED_TICK_MS
    }
    return TICK_MS + deps.random() * TICK_JITTER_MS
  }

  function schedule(): void {
    if (handle !== null || stopped) {
      return
    }
    handle = deps.schedule(() => {
      handle = null
      step()
    }, tickMs())
  }

  function step(): void {
    if (stopped) {
      return
    }
    const skip = MIN_STEP + Math.floor(deps.random() * STEP_JITTER)
    const next = text.indexOf(' ', count + skip)
    if (next === -1) {
      // The last word has no space after it, so the drain reveals it whole.
      if (ended) {
        count = text.length
        done = true
        notify()
      }
      return
    }
    count = next
    notify()
    schedule()
  }

  return {
    revealed: () => count,
    finished: () => done,
    received(next) {
      text = next
      schedule()
    },
    end() {
      ended = true
      schedule()
    },
    watch(listener) {
      listeners.add(listener)
    },
    stop() {
      stopped = true
      if (handle !== null) {
        deps.cancel(handle)
        handle = null
      }
      listeners.clear()
    },
  }
}
