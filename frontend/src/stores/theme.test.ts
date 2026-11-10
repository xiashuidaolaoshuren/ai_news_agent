import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  REVEAL_EASE,
  REVEAL_MS,
  applyTheme,
  resolveInitialTheme,
  runSetTheme,
  themeOrigin,
  useThemeStore,
} from '@/stores/theme'

describe('resolveInitialTheme', () => {
  it('uses stored dark over OS light', () => {
    expect(resolveInitialTheme('dark', false)).toBe('dark')
  })

  it('follows OS when nothing valid is stored', () => {
    expect(resolveInitialTheme(null, true)).toBe('dark')
    expect(resolveInitialTheme(null, false)).toBe('light')
  })

  it('ignores invalid stored values', () => {
    expect(resolveInitialTheme('system', false)).toBe('light')
    expect(resolveInitialTheme('invalid', true)).toBe('dark')
  })
})

describe('useThemeStore init', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.documentElement.removeAttribute('data-theme')
  })

  it('sets data-theme on html from resolved initial theme', () => {
    const store = useThemeStore()
    store.initFromDocument()
    expect(document.documentElement.dataset.theme).toBeDefined()
    expect(['light', 'dark']).toContain(document.documentElement.dataset.theme)
    expect(store.theme).toBe(document.documentElement.dataset.theme)
  })
})

describe('setTheme persistence', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    applyTheme('light')
  })

  it('persists user choice and sets data-theme', () => {
    const store = useThemeStore()
    store.setTheme('dark', { user: true })
    expect(localStorage.getItem('anra-theme')).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('does not write localStorage when user is false', () => {
    const store = useThemeStore()
    store.setTheme('dark', { user: false })
    expect(localStorage.getItem('anra-theme')).toBeNull()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})

describe('OS theme follow', () => {
  let changeHandler: ((event: MediaQueryListEvent) => void) | null = null

  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    applyTheme('light')
    changeHandler = null
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => {
        const listeners = new Set<(event: MediaQueryListEvent) => void>()
        const mql = {
          matches: query.includes('dark') ? false : false,
          media: query,
          addEventListener: (_: string, handler: (event: MediaQueryListEvent) => void) => {
            if (query.includes('color-scheme')) {
              changeHandler = handler
              listeners.add(handler)
            }
          },
          removeEventListener: (_: string, handler: (event: MediaQueryListEvent) => void) => {
            listeners.delete(handler)
          },
          dispatch(matches: boolean) {
            for (const handler of listeners) {
              handler({ matches, media: query } as MediaQueryListEvent)
            }
          },
        }
        return mql
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('follows OS changes only while no stored choice', () => {
    const store = useThemeStore()
    store.startOsListener()
    expect(changeHandler).not.toBeNull()
    changeHandler!({ matches: true, media: '(prefers-color-scheme: dark)' } as MediaQueryListEvent)
    expect(document.documentElement.dataset.theme).toBe('dark')

    applyTheme('light')
    localStorage.setItem('anra-theme', 'light')
    changeHandler!({ matches: true, media: '(prefers-color-scheme: dark)' } as MediaQueryListEvent)
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('removes OS listener on stop', () => {
    const removeSpy = vi.fn()
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: removeSpy,
      })),
    )
    const store = useThemeStore()
    store.startOsListener()
    store.stopOsListener()
    expect(removeSpy).toHaveBeenCalled()
  })
})

describe('setTheme instant fallback', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    applyTheme('light')
    document.documentElement.classList.remove('theme-snap')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    // @ts-expect-error cleanup test stub
    delete document.startViewTransition
  })

  it('skips view transition when reduced motion is preferred', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('reduce'),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    const start = vi.fn()
    document.startViewTransition = start

    runSetTheme('dark', { user: true, point: [10, 10] })
    expect(start).not.toHaveBeenCalled()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.classList.contains('theme-snap')).toBe(false)
  })

  it('skips view transition when API is missing', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    runSetTheme('dark', { user: true, point: [10, 10] })
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.classList.contains('theme-snap')).toBe(false)
  })
})

describe('setTheme reveal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    applyTheme('light')
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    vi.spyOn(document.documentElement, 'animate').mockImplementation(
      () => ({ cancel: vi.fn() }) as unknown as Animation,
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    // @ts-expect-error cleanup
    delete document.startViewTransition
  })

  it('leaves the snap to the transition callback, never before the capture', () => {
    document.startViewTransition = (() => ({
      ready: Promise.resolve(),
      finished: Promise.resolve(),
      skipTransition: vi.fn(),
    })) as unknown as typeof document.startViewTransition
    document.documentElement.classList.remove('theme-snap')

    runSetTheme('dark', { user: true, point: [10, 10] })

    // Adding the class here would recalculate the whole document before the
    // browser has taken its picture of the old theme.
    expect(document.documentElement.classList.contains('theme-snap')).toBe(false)
  })

  it('cancels each reveal animation once its transition finishes', async () => {
    const cancels = [vi.fn(), vi.fn()]
    let call = 0
    vi.mocked(document.documentElement.animate).mockImplementation(
      () => ({ cancel: cancels[call++] }) as unknown as Animation,
    )
    const resolvers: Array<() => void> = []
    document.startViewTransition = (callback: () => void) => {
      callback()
      return {
        ready: Promise.resolve(),
        finished: new Promise<void>((resolve) => resolvers.push(resolve)),
        skipTransition: vi.fn(),
      } as unknown as ViewTransition
    }

    runSetTheme('dark', { user: true, point: [10, 10] })
    await Promise.resolve()
    await Promise.resolve()
    // A newer toggle supersedes the first before it finishes.
    runSetTheme('light', { user: true, point: [10, 10] })
    await Promise.resolve()
    await Promise.resolve()
    resolvers.forEach((resolve) => resolve())
    await new Promise((resolve) => setTimeout(resolve, 0))

    // A finished fill: 'both' animation left alive keeps every later reveal off
    // the compositor, so both must be released.
    expect(cancels[0]).toHaveBeenCalledTimes(1)
    expect(cancels[1]).toHaveBeenCalledTimes(1)
  })

  it('animates grow to dark on new root pseudo', async () => {
    let captured: Record<string, unknown> | undefined
    let resolveFinished!: () => void
    const finished = new Promise<void>((resolve) => {
      resolveFinished = resolve
    })
    document.startViewTransition = (callback: () => void) => {
      callback()
      return {
        ready: Promise.resolve(),
        finished,
        skipTransition: vi.fn(),
      } as unknown as ViewTransition
    }

    runSetTheme('dark', { user: true, point: [100, 100] })
    await Promise.resolve()
    expect(document.documentElement.classList.contains('vt-shrink')).toBe(false)
    expect(document.documentElement.animate).toHaveBeenCalled()
    captured = vi.mocked(document.documentElement.animate).mock.calls[0]?.[1] as Record<
      string,
      unknown
    >
    expect(captured?.duration).toBe(REVEAL_MS)
    expect(captured?.easing).toBe(REVEAL_EASE)
    expect(captured?.pseudoElement).toBe('::view-transition-new(root)')
    resolveFinished()
  })

  it('animates shrink to light on old root pseudo', async () => {
    applyTheme('dark')
    let resolveFinished!: () => void
    const finished = new Promise<void>((resolve) => {
      resolveFinished = resolve
    })
    document.startViewTransition = (callback: () => void) => {
      callback()
      return {
        ready: Promise.resolve(),
        finished,
        skipTransition: vi.fn(),
      } as unknown as ViewTransition
    }

    runSetTheme('light', { user: true, point: [100, 100] })
    await Promise.resolve()
    expect(document.documentElement.classList.contains('vt-shrink')).toBe(true)
    const captured = vi.mocked(document.documentElement.animate).mock.calls.at(-1)?.[1] as Record<
      string,
      unknown
    >
    expect(captured?.pseudoElement).toBe('::view-transition-old(root)')
    resolveFinished()
  })

  it('keeps the update callback synchronous and lets state follow the snapshot', async () => {
    let updateCallback: (() => unknown) | undefined
    let resolveReady!: () => void
    document.startViewTransition = ((callback: () => unknown) => {
      updateCallback = callback
      return {
        ready: new Promise<void>((resolve) => {
          resolveReady = resolve
        }),
        finished: Promise.resolve(),
        skipTransition: vi.fn(),
      } as unknown as ViewTransition
    }) as typeof document.startViewTransition

    const store = useThemeStore()
    store.setTheme('dark', { user: true, point: [10, 10] })

    // The browser captures the old state before running the callback, so the
    // icon and labels must not have flipped yet.
    expect(store.theme).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')

    // Nothing may be pending on this return value: an async callback leaves the
    // old snapshot frozen until Vue has finished re-rendering.
    const returned = updateCallback?.()

    expect(returned).toBeUndefined()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(store.theme).toBe('light')

    resolveReady()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(store.theme).toBe('dark')
  })

  it('lets the store follow the applied theme when the transition is skipped', async () => {
    document.startViewTransition = ((callback: () => unknown) => {
      callback()
      return {
        ready: Promise.reject(new DOMException('skipped', 'AbortError')),
        finished: Promise.resolve(),
        skipTransition: vi.fn(),
      }
    }) as unknown as typeof document.startViewTransition

    const store = useThemeStore()
    store.setTheme('dark', { user: true, point: [10, 10] })
    await new Promise((resolve) => setTimeout(resolve, 0))

    // The callback already flipped the DOM; the switch must not stay behind.
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(store.theme).toBe('dark')
    expect(store.userChosen).toBe(true)
  })

  it('ignores the late ready of a transition the next toggle replaced', async () => {
    const readies: Array<() => void> = []
    document.startViewTransition = ((callback: () => unknown) => {
      callback()
      return {
        ready: new Promise<void>((resolve) => readies.push(resolve)),
        finished: Promise.resolve(),
        skipTransition: vi.fn(),
      }
    }) as unknown as typeof document.startViewTransition

    const store = useThemeStore()
    store.setTheme('dark', { user: true, point: [10, 10] })
    store.setTheme('light', { user: true, point: [10, 10] })
    readies[0]?.()
    readies[1]?.()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(store.theme).toBe('light')
  })

  it('applies the reactive theme without animation when the reveal is skipped', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query: string) => ({
        matches: query.includes('reduce'),
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )

    const store = useThemeStore()
    store.setTheme('dark', { user: true, point: [10, 10] })

    expect(store.theme).toBe('dark')
  })
})

describe('themeOrigin', () => {
  it('uses pointer coordinates for pointer activation', () => {
    expect(themeOrigin({ detail: 1, clientX: 40, clientY: 50 }, null)).toEqual([40, 50])
  })

  it('uses control center for keyboard activation', () => {
    const control = document.createElement('button')
    control.getBoundingClientRect = () =>
      ({
        left: 100,
        top: 200,
        width: 40,
        height: 20,
        right: 140,
        bottom: 220,
      }) as DOMRect
    expect(themeOrigin({ detail: 0, clientX: 0, clientY: 0 }, control)).toEqual([120, 210])
  })

  it('falls back to viewport center without a valid control', () => {
    vi.stubGlobal('innerWidth', 800)
    vi.stubGlobal('innerHeight', 600)
    expect(themeOrigin({ detail: 0, clientX: 0, clientY: 0 }, null)).toEqual([400, 300])
    vi.unstubAllGlobals()
  })
})
