/**
 * The prototype's `partial()`: the streaming reply is the finished render cut at
 * the reveal count, so the markup stays well formed while it types out.
 */

/** The text the reveal counts: every text node of a render, in reading order. */
export function plainText(html: string): string {
  const host = document.createElement('div')
  host.innerHTML = html
  return host.textContent ?? ''
}

/**
 * Cut a render at `count` characters of its plain text, with the blinking caret
 * right after the last revealed character and everything past the cut removed.
 * A count that runs past the whole render leaves it alone, as the prototype does.
 */
export function truncateAt(html: string, count: number): string {
  const host = document.createElement('div')
  host.innerHTML = html
  const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT)
  let left = count
  let node = walker.nextNode() as Text | null
  while (node !== null) {
    const length = node.data.length
    if (length < left) {
      left -= length
      node = walker.nextNode() as Text | null
      continue
    }
    node.data = node.data.slice(0, left)
    const caret = document.createElement('span')
    caret.className = 'caret'
    node.after(caret)
    // Everything after the cut belongs to text the reveal has not reached yet.
    let cursor: Node = caret
    while (cursor !== host) {
      while (cursor.nextSibling !== null) {
        cursor.nextSibling.remove()
      }
      cursor = cursor.parentNode as Node
    }
    return host.innerHTML
  }
  return html
}
