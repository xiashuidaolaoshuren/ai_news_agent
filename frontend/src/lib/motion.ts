/**
 * Prototype `anim()`: the stagger index never runs past the eighth element, so a
 * long digest keeps a bounded delay.
 */
export const MAX_STAGGER_INDEX = 8

/**
 * The inline `--i` a `.rise` element carries, in the prototype's own format.
 * `null` or `undefined` means "do not animate", which is what a transcript that
 * was simply loaded shows.
 */
export function riseStyle(index: number | null | undefined): string | undefined {
  if (index === null || index === undefined) {
    return undefined
  }
  return `--i:${Math.min(index, MAX_STAGGER_INDEX)}`
}

/**
 * The prototype's `reduced()` check. The CSS media query already flattens every
 * animation; script-driven delays ask this so a collapse or a height tween is
 * skipped outright instead of running at 1ms.
 */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}
