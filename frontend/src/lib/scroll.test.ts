import { describe, expect, it } from 'vitest'

import { shouldStickToBottom } from '@/lib/scroll'

describe('shouldStickToBottom', () => {
  it('follows new content while the reader is at the end', () => {
    expect(shouldStickToBottom({ scrollTop: 900, clientHeight: 600, scrollHeight: 1500 })).toBe(
      true,
    )
  })

  it('follows content that is a few pixels short of the end', () => {
    expect(shouldStickToBottom({ scrollTop: 860, clientHeight: 600, scrollHeight: 1500 })).toBe(
      true,
    )
  })

  it('stays where it is once the reader has scrolled away', () => {
    expect(shouldStickToBottom({ scrollTop: 200, clientHeight: 600, scrollHeight: 1500 })).toBe(
      false,
    )
  })
})
