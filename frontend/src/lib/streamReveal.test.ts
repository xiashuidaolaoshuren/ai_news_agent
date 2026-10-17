import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createStreamReveal, type StreamRevealDeps } from '@/lib/streamReveal'

/** The default deps, with the prototype's randomness pinned to a known value. */
function revealWith(overrides: Partial<StreamRevealDeps> = {}) {
  return createStreamReveal({ random: () => 0, ...overrides })
}

describe('createStreamReveal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reveals up to the next space at least six characters ahead', () => {
    const reveal = revealWith()

    reveal.received('Hello world again')
    vi.advanceTimersByTime(70)

    expect(reveal.revealed()).toBe(11)
  })

  it('holds at the received text and continues when more arrives', () => {
    const reveal = revealWith()

    reveal.received('Alpha beta')
    vi.advanceTimersByTime(130)
    expect(reveal.revealed()).toBe(0)

    reveal.received('Alpha beta gamma')
    vi.advanceTimersByTime(70)
    expect(reveal.revealed()).toBe(10)

    vi.advanceTimersByTime(2000)
    expect(reveal.revealed()).toBe(10)

    reveal.received('Alpha beta gamma delta')
    vi.advanceTimersByTime(70)
    expect(reveal.revealed()).toBe(16)
  })

  it('steps every 15 ms under reduced motion', () => {
    const reveal = revealWith({ reducedMotion: () => true })

    reveal.received('Alpha beta gamma delta')
    vi.advanceTimersByTime(14)
    expect(reveal.revealed()).toBe(0)

    vi.advanceTimersByTime(1)
    expect(reveal.revealed()).toBe(10)
  })

  it('drains the rest and finishes when the stream ends', () => {
    const reveal = revealWith()

    reveal.received('Alpha beta gamma delta')
    vi.advanceTimersByTime(70)
    expect(reveal.revealed()).toBe(10)

    reveal.end()
    vi.advanceTimersByTime(70)
    expect(reveal.revealed()).toBe(16)

    vi.advanceTimersByTime(70)
    expect(reveal.revealed()).toBe(22)
    expect(reveal.finished()).toBe(true)
  })

  it('notifies watchers on each step, including the final drain', () => {
    const reveal = revealWith()
    const seen: number[] = []
    reveal.watch(() => seen.push(reveal.revealed()))

    reveal.received('Alpha beta gamma delta')
    vi.advanceTimersByTime(70)
    expect(seen).toEqual([10])

    reveal.end()
    vi.advanceTimersByTime(140)
    expect(seen).toEqual([10, 16, 22])
  })

  it('stops ticking and notifying once stopped', () => {
    const reveal = revealWith()
    const seen: number[] = []
    reveal.watch(() => seen.push(reveal.revealed()))

    reveal.received('Alpha beta gamma delta')
    reveal.stop()
    vi.advanceTimersByTime(5000)

    expect(reveal.revealed()).toBe(0)
    expect(seen).toEqual([])
  })
})
