import type { DigestVm, EntryVm, HfVm, JuyaIssueVm, SectionVm, WarningVm } from '@/vm'

/** Entry for a GitHub source with the meta line and a preview card. */
export function githubEntry(over: Partial<EntryVm> = {}): EntryVm {
  return {
    key: 'github:1',
    kind: 'github',
    rank: 1,
    title: 'NVIDIA/OpenShell',
    url: 'https://github.com/NVIDIA/OpenShell',
    sourceName: 'github.com',
    host: 'github.com',
    summary: 'OpenShell is the safe, private runtime for autonomous AI agents.',
    whyItMatters: 'Sandboxed runtimes are becoming the standard answer for agent commands.',
    caveat: null,
    followUp: 'try',
    avatar: { type: 'image', src: 'https://avatars.test/nvidia.png', alt: 'NVIDIA' },
    previewUrl: 'https://opengraph.test/openshell.png',
    meta: 'Rust · 13,659 ★ · +2,503 today',
    ...over,
  }
}

/** Hugging Face row with its comparison table data. */
export function hfEntry(over: Partial<EntryVm> = {}): EntryVm {
  const hf: HfVm = {
    modelId: 'Edge0/Audio8-ASR-Infinite',
    trending: '1,479',
    downloads30d: '27,228',
    likes: '1,989',
    pipeline: 'automatic-speech-recognition',
    baseModel: null,
    variants: [],
  }
  return {
    key: 'hf:1',
    kind: 'huggingface',
    rank: 2,
    title: 'Edge0/Audio8-ASR-Infinite',
    url: 'https://huggingface.co/Edge0/Audio8-ASR-Infinite',
    sourceName: 'huggingface.co',
    host: 'huggingface.co',
    summary: null,
    whyItMatters: null,
    caveat: null,
    followUp: 'read',
    avatar: { type: 'neutral' },
    previewUrl: null,
    hf,
    ...over,
  }
}

/** Juya story with its issue grouping fields. */
export function juyaEntry(over: Partial<EntryVm> = {}): EntryVm {
  return {
    key: 'juya:1',
    kind: 'juya',
    rank: 3,
    title: 'Google 发布 Gemini 4 Argon',
    url: 'https://daily.juya.uk',
    sourceName: 'AI 早报 2026-10-01',
    host: 'daily.juya.uk',
    summary: 'Google released Gemini 4 Argon.',
    whyItMatters: 'A new Gemini generation moves the comparison baseline.',
    caveat: null,
    followUp: 'read',
    avatar: { type: 'none' },
    previewUrl: null,
    juya: { topic: 'Headlines', originalUrl: null },
    ...over,
  }
}

export function juyaIssue(over: Partial<JuyaIssueVm> = {}): JuyaIssueVm {
  return {
    issueId: 'issue-34',
    eyebrow: 'AI 早报 · 2026-10-01',
    coverUrl: 'https://cdn.test/juya-cover-20261001.png',
    coverAlt: 'Google 发布 Gemini 4 Argon',
    leadTitle: 'Google 发布 Gemini 4 Argon',
    issueUrl: 'https://daily.juya.uk',
    stories: [juyaEntry({ rank: 1 })],
    ...over,
  }
}

export function sectionVm(over: Partial<SectionVm> = {}): SectionVm {
  return {
    kind: 'github',
    label: 'GitHub',
    subtitle: 'Trending repositories',
    count: 1,
    rangeStart: 1,
    rangeEnd: 1,
    entries: [githubEntry()],
    ...over,
  }
}

export function warningVm(over: Partial<WarningVm> = {}): WarningVm {
  return {
    source: 'github',
    label: 'GitHub',
    code: 'timeout',
    message: 'Request timed out. 0 of 5 items returned; other sources completed normally.',
    ...over,
  }
}

export function digestVm(over: Partial<DigestVm> = {}): DigestVm {
  return {
    ref: 'd15',
    generatedAt: '2026-10-01T20:04:00',
    itemCount: 5,
    sourcesReturned: 2,
    sourcesTotal: 3,
    warnings: [],
    sections: [sectionVm()],
    ...over,
  }
}
