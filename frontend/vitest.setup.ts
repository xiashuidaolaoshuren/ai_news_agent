import { vi } from 'vitest'

if (typeof window.matchMedia !== 'function') {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

if (typeof document.documentElement.animate !== 'function') {
  document.documentElement.animate = vi.fn(() => ({}) as Animation)
}
