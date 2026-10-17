import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: false, breaks: true })

/** Elements the assistant reply is allowed to produce. No `img`, `style`, or raw HTML. */
const ALLOWED_TAGS = [
  'a',
  'blockquote',
  'br',
  'code',
  'del',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'li',
  'ol',
  'p',
  'pre',
  's',
  'strong',
  'table',
  'tbody',
  'td',
  'th',
  'thead',
  'tr',
  'ul',
]

/** Drop any link whose scheme is not `http(s)`; the API text is untrusted. */
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (!(node instanceof Element) || node.tagName !== 'A') {
    return
  }
  const href = node.getAttribute('href')
  if (href === null) {
    return
  }
  const scheme = href.trim().toLowerCase()
  if (!scheme.startsWith('http:') && !scheme.startsWith('https:')) {
    node.removeAttribute('href')
    return
  }
  node.setAttribute('target', '_blank')
  node.setAttribute('rel', 'noopener noreferrer')
})

/** Sanitize a fragment of assistant HTML against the allowlist. */
export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: ['href', 'align'],
    ALLOW_DATA_ATTR: false,
  })
}

/** Render assistant markdown to HTML for the `.md` reply block. */
export function renderMarkdown(source: string): string {
  const text = source.trim()
  if (text === '') {
    return ''
  }
  return sanitizeHtml(md.render(text))
}
