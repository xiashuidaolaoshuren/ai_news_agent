import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  HOVER_DELAY_MS,
  hoverPreview,
  hideHoverPreview,
  installHoverPreviewListeners,
  scheduleHoverPreview,
  showHoverPreviewNow,
} from '@/lib/useHoverPreview'

function previewLink(url?: string): HTMLAnchorElement {
  const anchor = document.createElement('a')
  anchor.textContent = 'openai/gpt-oss'
  anchor.href = 'https://github.com/openai/gpt-oss'
  if (url !== undefined) {
    anchor.dataset.preview = url
  }
  return anchor
}

describe('hover preview', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    hideHoverPreview()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('waits for the hover delay before showing the preview', () => {
    const anchor = previewLink('https://example.test/card.png')

    scheduleHoverPreview(anchor)
    vi.advanceTimersByTime(HOVER_DELAY_MS - 1)

    expect(hoverPreview.visible).toBe(false)

    vi.advanceTimersByTime(1)

    expect(hoverPreview.visible).toBe(true)
    expect(hoverPreview.src).toBe('https://example.test/card.png')
    expect(hoverPreview.alt).toContain('openai/gpt-oss')
  })

  it('never shows a preview for a link without a preview url', () => {
    const anchor = previewLink()

    scheduleHoverPreview(anchor)
    vi.advanceTimersByTime(HOVER_DELAY_MS * 4)

    expect(hoverPreview.visible).toBe(false)
    expect(hoverPreview.src).toBe(null)
  })

  it('cancels a pending preview when the pointer leaves', () => {
    const anchor = previewLink('https://example.test/card.png')

    scheduleHoverPreview(anchor)
    hideHoverPreview()
    vi.advanceTimersByTime(HOVER_DELAY_MS * 2)

    expect(hoverPreview.visible).toBe(false)
  })

  it('places the card inside the viewport', () => {
    const anchor = previewLink('https://example.test/card.png')

    scheduleHoverPreview(anchor)
    vi.advanceTimersByTime(HOVER_DELAY_MS)

    expect(hoverPreview.top).toBeGreaterThanOrEqual(8)
    expect(hoverPreview.left).toBeGreaterThanOrEqual(8)
  })

  describe('thread listeners', () => {
    let thread: HTMLElement
    let anchor: HTMLAnchorElement
    let uninstall: () => void

    beforeEach(() => {
      thread = document.createElement('div')
      anchor = previewLink('https://example.test/card.png')
      thread.append(anchor)
      document.body.append(thread)
      uninstall = installHoverPreviewListeners(thread)
    })

    afterEach(() => {
      uninstall()
      thread.remove()
    })

    it('hides the card when the pointer leaves the link', () => {
      showHoverPreviewNow(anchor)

      anchor.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }))

      expect(hoverPreview.visible).toBe(false)
    })

    it('hides the card when the thread scrolls', () => {
      showHoverPreviewNow(anchor)

      thread.dispatchEvent(new Event('scroll'))

      expect(hoverPreview.visible).toBe(false)
    })

    it('hides the card on Escape and stops the shell from also seeing it', () => {
      const shellListener = vi.fn()
      document.addEventListener('keydown', shellListener)
      showHoverPreviewNow(anchor)

      anchor.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))

      expect(hoverPreview.visible).toBe(false)
      expect(shellListener).not.toHaveBeenCalled()
      document.removeEventListener('keydown', shellListener)
    })

    it('shows the card on focus and hides it on blur', () => {
      anchor.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))

      expect(hoverPreview.visible).toBe(true)

      anchor.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))

      expect(hoverPreview.visible).toBe(false)
    })

    it('stops reacting once unmounted', () => {
      showHoverPreviewNow(anchor)

      uninstall()
      showHoverPreviewNow(anchor)
      anchor.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }))

      expect(hoverPreview.visible).toBe(true)
    })
  })
})
