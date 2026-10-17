/** Enough of a scroll container to decide whether its end is in view. */
export interface ScrollBox {
  scrollTop: number
  clientHeight: number
  scrollHeight: number
}

/** How far short of the end still counts as reading the newest content. */
const STICK_SLACK_PX = 48

/**
 * True while the reader is at the end of a scroll container, which is what lets
 * new content scroll itself into view. Once they scroll away it stays put.
 */
export function shouldStickToBottom(box: ScrollBox): boolean {
  return box.scrollHeight - box.scrollTop - box.clientHeight <= STICK_SLACK_PX
}
