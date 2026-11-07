import { describe, expect, it } from 'vitest'

import {
  healthHint,
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
      { name: 'juya', label: 'Juya', kind: 'juya', default: true, health: 'unchecked' },
      {
        name: 'huggingface',
        label: 'Hugging Face',
        kind: 'huggingface',
        default: false,
        health: 'unchecked',
      },
      { name: 'github', label: 'GitHub', kind: 'github', default: false, health: 'unchecked' },
      { name: 'zhihu', label: 'Zhihu', kind: 'zhihu', default: false, health: 'unchecked' },
      { name: 'bilibili', label: 'Bilibili', kind: 'bilibili', default: false, health: 'unchecked' },
    ])
  })

  it('reads the credential health the catalog carries for the current version', () => {
    const options = parseSources({
      sources: [
        {
          name: 'github',
          default: false,
          health: {
            current: 'auth_error',
            stale: false,
            credential_version: 'v1',
            observed_at: '2026-10-01T19:58:00Z',
            kind: 'connector',
          },
        },
        {
          name: 'huggingface',
          default: false,
          health: {
            current: null,
            stale: true,
            credential_version: 'v2',
            observed_at: null,
            kind: null,
          },
        },
        { name: 'juya', default: true },
      ],
    })

    expect(options.map((option) => option.health)).toEqual(['auth_error', 'stale', 'unchecked'])
  })

  it('explains only the health states a chip can show', () => {
    expect(healthHint('auth_error')).toBe('Last check: authentication error.')
    expect(healthHint('stale')).toBe('Not checked since update.')
    expect(healthHint('timeout')).toBe('Last check: timed out.')
    expect(healthHint('ok')).toBe(null)
    expect(healthHint('unchecked')).toBe(null)
  })

  it('keeps a connector the client does not know, without a logo', () => {
    expect(parseSources({ sources: [{ name: 'reddit', default: true }] })).toEqual([
      { name: 'reddit', label: 'reddit', kind: null, default: true, health: 'unchecked' },
    ])
  })

  it('returns an empty list when the payload carries no catalog', () => {
    expect(parseSources(null)).toEqual([])
    expect(parseSources({ sources: 'nope' })).toEqual([])
  })
})

describe('prefsFor', () => {
  const options = parseSources(CATALOG)

  it('shows the catalog defaults before the first PATCH', () => {
    expect(prefsFor(null, options)).toEqual({ selected: ['juya'] })
  })

  it('prefers the sources the session already stores', () => {
    const session = { connector_names: ['github', 'zhihu'] }
    expect(prefsFor(session, options)).toEqual({ selected: ['github', 'zhihu'] })
  })
})

describe('validateComposer', () => {
  const valid = { text: 'What shipped?', selected: ['juya'] }

  it('accepts a question with one source', () => {
    expect(validateComposer(valid)).toEqual({})
  })

  it('requires text beyond whitespace', () => {
    expect(validateComposer({ ...valid, text: '   ' })).toEqual({ text: TEXT_REQUIRED })
  })

  it('requires at least one source', () => {
    expect(validateComposer({ ...valid, selected: [] })).toEqual({ sources: SOURCE_REQUIRED })
  })

  it('reports every failing rule at once', () => {
    expect(validateComposer({ text: '  ', selected: [] })).toEqual({
      text: TEXT_REQUIRED,
      sources: SOURCE_REQUIRED,
    })
  })
})
