import { describe, expect, it } from 'vitest'

import { renderMarkdown, sanitizeHtml } from '@/lib/markdown'

describe('renderMarkdown', () => {
  it('renders headings, paragraphs, lists, code, and blockquotes', () => {
    const html = renderMarkdown(
      [
        '### Top open-weight models',
        '',
        'A short **bolder** summary with `inline code`.',
        '',
        '- first item',
        '- second item',
        '',
        '> quoted line',
        '',
        '```ts',
        'const a = 1',
        '```',
      ].join('\n'),
    )

    expect(html).toContain('<h3>Top open-weight models</h3>')
    expect(html).toContain('<strong>bolder</strong>')
    expect(html).toContain('<code>inline code</code>')
    expect(html).toContain('<li>first item</li>')
    expect(html).toContain('<li>second item</li>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('<pre>')
  })

  it('returns an empty string for empty input', () => {
    expect(renderMarkdown('')).toBe('')
  })

  it('drops images the API markdown carries', () => {
    const html = renderMarkdown('![chart](https://evil.test/track.png)')

    expect(html).not.toContain('<img')
    expect(html).not.toContain('evil.test/track.png')
  })

  it('strips scripts, event handlers, images, and non-http urls', () => {
    const html = sanitizeHtml(
      [
        '<script>alert(1)</script>',
        '<a href="javascript:alert(1)" onclick="steal()">x</a>',
        '<img src="https://tracker.test/p.png" onerror="boom()">',
        '<a href="https://example.test/docs">docs</a>',
      ].join(''),
    )

    expect(html).not.toContain('<script')
    expect(html).not.toContain('onclick')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('href="https://example.test/docs"')
  })

  it('opens rendered links in a new tab without a referrer leak', () => {
    const html = renderMarkdown('[docs](https://example.test/docs)')
    const doc = new DOMParser().parseFromString(html, 'text/html')
    const anchor = doc.querySelector('a')

    expect(anchor?.getAttribute('target')).toBe('_blank')
    expect(anchor?.getAttribute('rel')).toContain('noopener')
  })
})
