import { describe, expect, it } from 'vitest'

import type {
  DigestEntryView,
  JuyaDigestEntryView,
  SourceKind,
} from '@/api/generated/types.gen'
import { toDigestVm, toSectionsVm, toWarningVm } from '@/vm'

function entry(kind: SourceKind, rank: number, id?: string): DigestEntryView {
  return {
    source_kind: kind as DigestEntryView['source_kind'],
    source_id: id ?? `${kind}-${rank}`,
    title: `${kind} item ${rank}`,
    source_name: kind,
    source_url: `https://example.com/${rank}`,
    summary: 's',
    why_it_matters: 'w',
    background_knowledge: 'b',
    follow_up_action: 'read',
    display_rank: rank,
  }
}

describe('toSectionsVm', () => {
  it('groups contiguous runs of one source kind', () => {
    const sections = toSectionsVm([
      entry('juya', 1),
      entry('juya', 2),
      entry('github', 3),
      entry('github', 4),
      entry('github', 5),
      entry('huggingface', 6),
    ])

    expect(sections.map((section) => section.kind)).toEqual([
      'juya',
      'github',
      'huggingface',
    ])
    expect(sections[0]?.count).toBe(2)
    expect(sections[1]?.count).toBe(3)
    expect(sections[2]?.count).toBe(1)
  })

  it('uses the first and last display rank of the run as the range', () => {
    const sections = toSectionsVm([
      entry('github', 4),
      entry('github', 5),
      entry('github', 6),
    ])

    expect(sections[0]?.rangeStart).toBe(4)
    expect(sections[0]?.rangeEnd).toBe(6)
  })

  it('splits interleaved kinds into separate sections and keeps ranges continuous', () => {
    const sections = toSectionsVm([
      entry('juya', 1),
      entry('github', 2),
      entry('juya', 3),
      entry('github', 4),
    ])

    expect(sections.map((section) => [section.kind, section.rangeStart, section.rangeEnd])).toEqual([
      ['juya', 1, 1],
      ['github', 2, 2],
      ['juya', 3, 3],
      ['github', 4, 4],
    ])
  })

  it('labels each section with the source name and subtitle', () => {
    const sections = toSectionsVm([
      entry('juya', 1),
      entry('github', 2),
      entry('huggingface', 3),
      entry('zhihu', 4),
    ])

    expect(sections.map((section) => [section.label, section.subtitle])).toEqual([
      ['Juya', '橘鸦 AI 早报'],
      ['GitHub', 'Trending repositories'],
      ['Hugging Face', 'Trending models'],
      ['Zhihu', null],
    ])
  })

  it('returns no sections for no entries', () => {
    expect(toSectionsVm([])).toEqual([])
  })
})

function juyaEntry(
  title: string,
  rank: number,
  overrides: Partial<JuyaDigestEntryView> = {},
): JuyaDigestEntryView {
  return {
    source_kind: 'juya',
    source_id: `juya-${rank}`,
    title,
    source_name: 'Juya',
    source_url: 'https://daily.juya.uk',
    summary: 's',
    why_it_matters: 'w',
    background_knowledge: 'b',
    follow_up_action: 'read',
    display_rank: rank,
    item_type: 'story',
    ...overrides,
  }
}

describe('Juya issue grouping', () => {
  it('groups stories under one issue cover', () => {
    const issue = {
      id: 'juya-2026-10-01',
      date: '2026-10-01',
      url: 'https://daily.juya.uk/2026-10-01',
      cover_url: 'https://daily.juya.uk/cover.png',
      lead_title: 'Google 发布 Gemini 4 Argon',
    }
    const sections = toSectionsVm([
      juyaEntry('Google 发布 Gemini 4 Argon', 1, {
        issue,
        story: { number: 1, section: 'Headlines', original_url: 'https://example.com/1' },
      }),
      juyaEntry('蚂蚁百灵发布 Ling 3.1 flash', 2, {
        issue,
        story: { number: 4, section: 'Model releases', original_url: 'https://example.com/4' },
      }),
    ])

    expect(sections[0]?.juyaIssues).toHaveLength(1)
    const group = sections[0]?.juyaIssues?.[0]
    expect(group?.issueId).toBe('juya-2026-10-01')
    expect(group?.coverUrl).toBe('https://daily.juya.uk/cover.png')
    expect(group?.coverAlt).toBe('Google 发布 Gemini 4 Argon')
    expect(group?.leadTitle).toBe('Google 发布 Gemini 4 Argon')
    expect(group?.stories).toHaveLength(2)
    expect(group?.stories[0]?.juya).toEqual({
      topic: 'Headlines',
      originalUrl: 'https://example.com/1',
    })
    expect(group?.stories[1]?.juya).toEqual({
      topic: 'Model releases',
      originalUrl: 'https://example.com/4',
    })
  })

  it('builds the eyebrow from the issue date with no issue number', () => {
    const sections = toSectionsVm([
      juyaEntry('A', 1, {
        issue: { id: 'i1', date: '2026-10-01', cover_url: 'https://x.example/c.png' },
      }),
    ])

    expect(sections[0]?.juyaIssues?.[0]?.eyebrow).toBe('AI 早报 · 2026-10-01')
    expect(sections[0]?.juyaIssues?.[0]?.eyebrow).not.toMatch(/No\.|#\d/)
  })

  it('omits the date from the eyebrow when the issue has none', () => {
    const sections = toSectionsVm([juyaEntry('A', 1, { issue: { id: 'i1' } })])

    expect(sections[0]?.juyaIssues?.[0]?.eyebrow).toBe('AI 早报')
  })

  it('keeps separate groups for separate issues in order', () => {
    const sections = toSectionsVm([
      juyaEntry('A', 1, {
        issue: { id: 'i1', date: '2026-10-01', cover_url: 'https://x.example/1.png' },
      }),
      juyaEntry('B', 2, {
        issue: { id: 'i2', date: '2026-09-21', cover_url: 'https://x.example/2.png' },
      }),
    ])

    expect(sections[0]?.juyaIssues?.map((group) => group.issueId)).toEqual(['i1', 'i2'])
    expect(sections[0]?.juyaIssues?.map((group) => group.eyebrow)).toEqual([
      'AI 早报 · 2026-10-01',
      'AI 早报 · 2026-09-21',
    ])
  })

  it('falls back to one coverless group when stories carry no issue id', () => {
    const sections = toSectionsVm([juyaEntry('A', 1), juyaEntry('B', 2)])

    expect(sections[0]?.juyaIssues).toHaveLength(1)
    expect(sections[0]?.juyaIssues?.[0]?.coverUrl).toBeNull()
    expect(sections[0]?.juyaIssues?.[0]?.eyebrow).toBe('AI 早报')
    expect(sections[0]?.juyaIssues?.[0]?.stories).toHaveLength(2)
  })

  it('never keeps a non-http cover or story url', () => {
    const sections = toSectionsVm([
      juyaEntry('A', 1, {
        issue: { id: 'i1', date: '2026-10-01', cover_url: 'javascript:alert(1)' },
        story: { number: 1, section: 'Headlines', original_url: 'javascript:alert(1)' },
      }),
    ])

    expect(sections[0]?.juyaIssues?.[0]?.coverUrl).toBeNull()
    expect(sections[0]?.juyaIssues?.[0]?.stories[0]?.juya?.originalUrl).toBeNull()
  })
})

describe('toDigestVm', () => {
  const digest = {
    generated_at: '2026-10-01T20:04:00Z',
    entries: [entry('juya', 1), entry('github', 2), entry('github', 3), entry('huggingface', 4)],
  }

  it('builds the dN ref, item count, and sections', () => {
    const vm = toDigestVm({ digest, digestId: 15 })

    expect(vm.ref).toBe('d15')
    expect(vm.generatedAt).toBe('2026-10-01T20:04:00Z')
    expect(vm.itemCount).toBe(4)
    expect(vm.sections.map((section) => section.kind)).toEqual([
      'juya',
      'github',
      'huggingface',
    ])
    expect(vm.warnings).toEqual([])
  })

  it('has a null ref when the digest id is unknown', () => {
    expect(toDigestVm({ digest, digestId: null }).ref).toBeNull()
    expect(toDigestVm({ digest }).ref).toBeNull()
  })

  it('counts sources returned against the session selected sources', () => {
    const vm = toDigestVm({
      digest,
      digestId: 15,
      connectorNames: ['juya', 'huggingface', 'github', 'zhihu', 'bilibili'],
      warnings: [
        { connector: 'zhihu', code: 'no_items', message: 'Connector returned no items.' },
        { connector: 'bilibili', code: 'timeout', message: 'Request timed out.' },
      ],
    })

    expect(vm.sourcesReturned).toBe(3)
    expect(vm.sourcesTotal).toBe(5)
    expect(vm.warnings).toHaveLength(2)
  })

  it('falls back to entry kinds and warnings when the session has no preference', () => {
    const vm = toDigestVm({
      digest,
      digestId: 15,
      connectorNames: null,
      warnings: [{ connector: 'zhihu', code: 'no_items', message: 'No items.' }],
    })

    expect(vm.sourcesReturned).toBe(3)
    expect(vm.sourcesTotal).toBe(4)
  })

  it('handles an empty digest', () => {
    const vm = toDigestVm({
      digest: { generated_at: '2026-10-01T20:04:00Z', entries: [] },
      digestId: 12,
    })

    expect(vm.itemCount).toBe(0)
    expect(vm.sections).toEqual([])
    expect(vm.sourcesReturned).toBe(0)
    expect(vm.sourcesTotal).toBe(0)
  })
})

describe('toWarningVm', () => {
  it('labels the warning with the source display name', () => {
    expect(
      toWarningVm({
        connector: 'huggingface',
        code: 'owner_profile_unavailable',
        message: 'Owner profile could not be fetched.',
        detail: 'rate limited',
      }),
    ).toEqual({
      source: 'huggingface',
      label: 'Hugging Face',
      code: 'owner_profile_unavailable',
      message: 'Owner profile could not be fetched.',
    })
  })

  it('falls back to the raw connector name for an unknown source', () => {
    expect(
      toWarningVm({ connector: 'mystery', code: 'x', message: 'Something happened.' }),
    ).toMatchObject({ source: 'mystery', label: 'mystery' })
  })
})
