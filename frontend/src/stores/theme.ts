import { defineStore } from 'pinia'
import { nextTick, ref } from 'vue'

import { prefersReducedMotion } from '@/lib/motion'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'anra-theme'
export const REVEAL_MS = 600
export const REVEAL_EASE = 'cubic-bezier(.25,.8,.3,1)'

function isTheme(value: string | null | undefined): value is Theme {
  return value === 'light' || value === 'dark'
}

export function resolveInitialTheme(
  stored: string | null,
  osDark: boolean,
): Theme {
  if (isTheme(stored)) {
    return stored
  }
  return osDark ? 'dark' : 'light'
}

export function readStoredTheme(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function hasStoredThemeChoice(): boolean {
  return isTheme(readStoredTheme())
}

function prefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  root.classList.add('theme-snap')
  root.dataset.theme = theme
  void getComputedStyle(root).color
}

export function themeOrigin(
  event: Pick<MouseEvent, 'detail' | 'clientX' | 'clientY'> | null | undefined,
  control: HTMLElement | null | undefined,
): [number, number] {
  if (event && event.detail > 0 && (event.clientX || event.clientY)) {
    return [event.clientX, event.clientY]
  }
  const rect = control?.getBoundingClientRect()
  if (
    rect &&
    rect.width &&
    rect.right > 0 &&
    rect.left < window.innerWidth &&
    rect.bottom > 0 &&
    rect.top < window.innerHeight
  ) {
    return [rect.left + rect.width / 2, rect.top + rect.height / 2]
  }
  return [window.innerWidth / 2, window.innerHeight / 2]
}

let themeViewTransition: ViewTransition | null = null

export function runSetTheme(
  theme: Theme,
  options: {
    user?: boolean
    point?: [number, number]
    onApply?: () => void | Promise<void>
  } = {},
): void {
  const user = options.user === true
  const root = document.documentElement
  const current = isTheme(root.dataset.theme) ? root.dataset.theme : 'light'

  if (user) {
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* ignore */
    }
  }

  if (
    !user ||
    theme === current ||
    prefersReducedMotion() ||
    typeof document.startViewTransition !== 'function'
  ) {
    if (themeViewTransition) {
      themeViewTransition.skipTransition()
    }
    applyTheme(theme)
    void options.onApply?.()
    root.classList.remove('theme-snap')
    return
  }

  const [x, y] = options.point ?? themeOrigin(null, null)
  const radius = Math.ceil(
    Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y)),
  )
  const grow = theme === 'dark'
  const points = [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`]

  root.classList.add('theme-snap')
  root.classList.add('vt-theme')
  root.classList.toggle('vt-shrink', !grow)

  const vt = document.startViewTransition(async () => {
    applyTheme(theme)
    // Inside the callback so the icon and labels flip with the reveal instead of
    // landing in the snapshot of the old theme.
    await options.onApply?.()
  })
  themeViewTransition = vt

  void vt.ready
    .then(() =>
      root.animate(
        { clipPath: grow ? points : [...points].reverse() },
        {
          duration: REVEAL_MS,
          easing: REVEAL_EASE,
          fill: 'both',
          pseudoElement: grow
            ? '::view-transition-new(root)'
            : '::view-transition-old(root)',
        },
      ),
    )
    .catch(() => {})

  void vt.finished.finally(() => {
    if (themeViewTransition !== vt) {
      return
    }
    themeViewTransition = null
    root.classList.remove('vt-theme', 'vt-shrink', 'theme-snap')
  })
}

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<Theme>('light')
  const userChosen = ref(false)
  let osMedia: MediaQueryList | null = null
  let osHandler: ((event: MediaQueryListEvent) => void) | null = null

  function syncFromDom(): void {
    const onDom = document.documentElement.dataset.theme
    if (isTheme(onDom)) {
      theme.value = onDom
    }
    userChosen.value = hasStoredThemeChoice()
  }

  function initFromDocument(): void {
    syncFromDom()
    if (!isTheme(document.documentElement.dataset.theme)) {
      const resolved = resolveInitialTheme(readStoredTheme(), prefersDark())
      applyTheme(resolved)
      theme.value = resolved
    }
    userChosen.value = hasStoredThemeChoice()
    startOsListener()
  }

  function setTheme(
    next: Theme,
    options: { user?: boolean; point?: [number, number]; event?: MouseEvent | null; control?: HTMLElement | null } = {},
  ): void {
    const point =
      options.point ??
      themeOrigin(options.event ?? null, options.control ?? null)
    runSetTheme(next, {
      user: options.user,
      point,
      onApply: () => {
        theme.value = next
        userChosen.value = options.user === true || hasStoredThemeChoice()
        return nextTick()
      },
    })
  }

  function toggleTheme(event?: MouseEvent, control?: HTMLElement | null): void {
    setTheme(theme.value === 'dark' ? 'light' : 'dark', {
      user: true,
      event: event ?? null,
      control: control ?? null,
    })
  }

  function startOsListener(): void {
    stopOsListener()
    osMedia = window.matchMedia('(prefers-color-scheme: dark)')
    osHandler = (event: MediaQueryListEvent) => {
      if (hasStoredThemeChoice()) {
        return
      }
      const next: Theme = event.matches ? 'dark' : 'light'
      runSetTheme(next, { user: false })
      theme.value = next
      userChosen.value = false
    }
    osMedia.addEventListener('change', osHandler)
  }

  function stopOsListener(): void {
    if (osMedia && osHandler) {
      osMedia.removeEventListener('change', osHandler)
    }
    osMedia = null
    osHandler = null
  }

  return {
    theme,
    userChosen,
    initFromDocument,
    setTheme,
    toggleTheme,
    startOsListener,
    stopOsListener,
  }
})

/** Alias for plan handoff (`useTheme()`). */
export const useTheme = useThemeStore
