import { describe, expect, it } from 'vitest'

import { plainText, truncateAt } from '@/lib/revealHtml'

describe('plainText', () => {
  it('reads the render in the order the reveal counts it', () => {
    expect(plainText('<p>Alpha <b>beta</b></p><ul><li>gamma</li></ul>')).toBe(
      'Alpha betagamma',
    )
  })
})

describe('truncateAt', () => {
  it('cuts inside a nested element and parks the caret after the cut', () => {
    expect(truncateAt('<p>Alpha <b>beta</b> gamma</p>', 8)).toBe(
      '<p>Alpha <b>be<span class="caret"></span></b></p>',
    )
  })

  it('keeps an empty block with the caret alone before the first character', () => {
    expect(truncateAt('<p>Alpha</p>', 0)).toBe('<p><span class="caret"></span></p>')
  })

  it('parks the caret at the end when the count covers the whole render', () => {
    expect(truncateAt('<p>Alpha</p>', 5)).toBe(
      '<p>Alpha<span class="caret"></span></p>',
    )
  })
})
