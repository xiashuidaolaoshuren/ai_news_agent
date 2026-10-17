import { reactive, readonly } from 'vue'

/** Hover dwell before a preview card appears, from the prototype. */
export const HOVER_DELAY_MS = 400

/** Fallback card height used only when the card element has not been measured. */
const FALLBACK_CARD_HEIGHT = 220
const CARD_WIDTH = 320
const EDGE_GAP = 8

export interface HoverPreviewState {
  visible: boolean
  src: string | null
  alt: string
  caption: string
  top: number
  left: number
}

const state = reactive<HoverPreviewState>({
  visible: false,
  src: null,
  alt: '',
  caption: '',
  top: EDGE_GAP,
  left: EDGE_GAP,
})

/** The single preview card the thread renders. Read-only for consumers. */
export const hoverPreview = readonly(state)

let timer: ReturnType<typeof setTimeout> | null = null
let cardEl: HTMLElement | null = null

function isHttpUrl(value: string): boolean {
  const scheme = value.trim().toLowerCase()
  return scheme.startsWith('http:') || scheme.startsWith('https:')
}

/** The preview card element, measured for placement while it is visible. */
export function registerHoverCard(el: HTMLElement | null): void {
  cardEl = el
}

function place(anchor: Element): void {
  const rect = anchor.getBoundingClientRect()
  const height = cardEl?.offsetHeight ?? FALLBACK_CARD_HEIGHT
  let top = rect.bottom + EDGE_GAP
  if (top + height > window.innerHeight - EDGE_GAP) {
    top = rect.top - height - EDGE_GAP
  }
  state.top = Math.max(EDGE_GAP, top)
  state.left = Math.max(EDGE_GAP, Math.min(rect.left, window.innerWidth - CARD_WIDTH - EDGE_GAP))
}

function show(anchor: Element): void {
  const url = (anchor as HTMLElement).dataset.preview ?? ''
  if (!isHttpUrl(url)) {
    return
  }
  state.src = url
  state.alt = `GitHub preview card for ${anchor.textContent ?? ''}`.trim()
  state.caption = captionFor(anchor)
  place(anchor)
  state.visible = true
}

/** `Preview card · github.com` for the previewed link; empty when it has no host. */
function captionFor(anchor: Element): string {
  const href = (anchor as HTMLAnchorElement).href ?? ''
  if (!isHttpUrl(href)) {
    return ''
  }
  try {
    const host = new URL(href).hostname.replace(/^www\./, '')
    return `Preview card · ${host}`
  } catch {
    return ''
  }
}

/** Show the card for a link that is already focused, with no dwell delay. */
export function showHoverPreviewNow(anchor: Element): void {
  clearHoverTimer()
  show(anchor)
}

function clearHoverTimer(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

/** Start the dwell timer for a link; links without a preview url are ignored. */
export function scheduleHoverPreview(anchor: Element): void {
  clearHoverTimer()
  if (!isHttpUrl((anchor as HTMLElement).dataset.preview ?? '')) {
    return
  }
  timer = setTimeout(() => {
    timer = null
    show(anchor)
  }, HOVER_DELAY_MS)
}

/** Hide the card and cancel any pending dwell. */
export function hideHoverPreview(): void {
  clearHoverTimer()
  state.visible = false
  state.src = null
  state.alt = ''
  state.caption = ''
}

function previewLinkFrom(event: Event): HTMLElement | null {  const target = event.target
  if (!(target instanceof Element)) {
    return null
  }
  const link = target.closest('[data-preview]')
  return link instanceof HTMLElement ? link : null
}

/**
 * Watch a thread container for preview links and dismiss the card on scroll,
 * pointer-out, blur, or Escape. Returns the cleanup for `onUnmounted`.
 */
export function installHoverPreviewListeners(container: HTMLElement): () => void {
  const onMouseOver = (event: Event) => {
    const link = previewLinkFrom(event)
    if (link !== null) {
      scheduleHoverPreview(link)
    }
  }
  const onMouseOut = (event: Event) => {
    if (previewLinkFrom(event) !== null) {
      hideHoverPreview()
    }
  }
  const onFocusIn = (event: Event) => {
    const link = previewLinkFrom(event)
    if (link !== null) {
      showHoverPreviewNow(link)
    }
  }
  const onFocusOut = (event: Event) => {
    if (previewLinkFrom(event) !== null) {
      hideHoverPreview()
    }
  }
  const onScroll = () => {
    hideHoverPreview()
  }
  const onKeydown = (event: KeyboardEvent) => {
    if (event.key !== 'Escape' || !state.visible) {
      return
    }
    // Consume the press so the shell does not also close an overlay.
    event.stopPropagation()
    hideHoverPreview()
  }

  container.addEventListener('mouseover', onMouseOver)
  container.addEventListener('mouseout', onMouseOut)
  container.addEventListener('focusin', onFocusIn)
  container.addEventListener('focusout', onFocusOut)
  container.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('keydown', onKeydown, true)

  return () => {
    container.removeEventListener('mouseover', onMouseOver)
    container.removeEventListener('mouseout', onMouseOut)
    container.removeEventListener('focusin', onFocusIn)
    container.removeEventListener('focusout', onFocusOut)
    container.removeEventListener('scroll', onScroll)
    window.removeEventListener('keydown', onKeydown, true)
    hideHoverPreview()
  }
}
