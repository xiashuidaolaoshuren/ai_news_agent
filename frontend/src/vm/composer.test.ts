import { describe, expect, it } from 'vitest'

import {
  COUNT_INVALID,
  parseSources,
  prefsFor,
  TEXT_REQUIRED,
  SOURCE_REQUIRED,
  validateComposer,
} from '@/vm/composer'

/** Shape of `GET /api/v1/sources`, which the generated client types as `unknown`. */
const CATALOG = {
  defaults: ['juya'],
  sources: [
    { name: 'juya', default: true, opt_in: false },
    { name: 'huggingface', default: false, opt_in: true },
    { name: 'github', default: false, opt_in: true },
    { name: 'zhihu', default: false, opt_in: true },
    { name: 'bilibili', default: false, opt_in: true },
  ],
}

describe('parseSources', () => {
  it('labels each catalog entry in the order the API returns it', () => {
    expect(parseSources(CATALOG)).toEqual([
      { name: 'juya', label: 'Juya', kind: 'juya', default: true },
      { name: 'huggingface', label: 'Hugging Face', kind: 'huggingface', default: false },
      { name: 'github', label: 'GitHub', kind: 'github', default: false },
      { name: 'zhihu', label: 'Zhihu', kind: 'zhihu', default: false },
      { name: 'bilibili', label: 'Bilibili', kind: 'bilibili', default: false },
    ])
  })

  it('keeps a connector the client does not know, without a logo', () => {
    expect(parseSources({ sources: [{ name: 'reddit', default: true }] })).toEqual([
      { name: 'reddit', label: 'reddit', kind: null, default: true },
    ])
  })

  it('returns an empty list when the payload carries no catalog', () => {
    expect(parseSources(null)).toEqual([])
    expect(parseSources({ sources: 'nope' })).toEqual([])
  })
})

describe('prefsFor', () => {
  const options = parseSources(CATALOG)

  it('shows the catalog defaults and a count of 5 before the first PATCH', () => {
    expect(prefsFor(null, options)).toEqual({ selected: ['juya'], count: '5' })
  })

  it('prefers the preferences the session already stores', () => {
    const session = { connector_names: ['github', 'zhihu'], items_per_source: 8 }
    expect(prefsFor(session, options)).toEqual({ selected: ['github', 'zhihu'], count: '8' })
  })
})

describe('validateComposer', () => {
  const valid = { text: 'What shipped?', selected: ['juya'], count: '5' }

  it('accepts a question with one source and a count in range', () => {
    expect(validateComposer(valid)).toEqual({})
  })

  it('requires text beyond whitespace', () => {
    expect(validateComposer({ ...valid, text: '   ' })).toEqual({ text: TEXT_REQUIRED })
  })

  it('requires at least one source', () => {
    expect(validateComposer({ ...valid, selected: [] })).toEqual({ sources: SOURCE_REQUIRED })
  })

  it('rejects a count that is not a whole number from 1 to 20', () => {
    expect(validateComposer({ ...valid, count: '' }).count).toBe(COUNT_INVALID)
    expect(validateComposer({ ...valid, count: '0' }).count).toBe(COUNT_INVALID)
    expect(validateComposer({ ...valid, count: '21' }).count).toBe(COUNT_INVALID)
    expect(validateComposer({ ...valid, count: '3.5' }).count).toBe(COUNT_INVALID)
    expect(validateComposer({ ...valid, count: 'abc' }).count).toBe(COUNT_INVALID)
    expect(validateComposer({ ...valid, count: '20' })).toEqual({})
  })

  it('reports every failing rule at once', () => {
    expect(validateComposer({ text: '  ', selected: [], count: 'x' })).toEqual({
      text: TEXT_REQUIRED,
      sources: SOURCE_REQUIRED,
      count: COUNT_INVALID,
    })
  })
})
