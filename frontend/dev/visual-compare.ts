/**
 * Visual-compare entry. Renders the prototype fixtures through the production
 * components so the thread, digest reply, and hover card can be compared against
 * the approved OpenDesign prototype. Not part of the app build.
 */
import { createApp, h, ref } from 'vue'

import '@/style.css'

import Thread from '@/components/thread/Thread.vue'

import type { DigestVm, EntryVm, JuyaIssueVm, MessageVm, SectionVm } from '@/vm'
import { HF_FIXTURES, JUYA_FIXTURES, GH_FIXTURES } from '@/vm/fixtures/prototype'
import { toVmFromFixture } from '@/vm/fixtures/toVmFromFixture'

const juya = JUYA_FIXTURES.map(toVmFromFixture)
const hf = HF_FIXTURES.map(toVmFromFixture)
const github = GH_FIXTURES.map(toVmFromFixture)

// Fixture assets are served beside this page. The hover card only accepts http(s)
// urls, as the API data does, so resolve them against the dev server here.
for (const entry of github) {
  entry.previewUrl = entry.previewUrl === null ? null : new URL(entry.previewUrl, window.location.href).href
}

function range(entries: EntryVm[]): [number, number] {
  return [entries[0]?.rank ?? 0, entries[entries.length - 1]?.rank ?? 0]
}

function section(kind: SectionVm['kind'], label: string, subtitle: string, entries: EntryVm[]): SectionVm {
  const [rangeStart, rangeEnd] = range(entries)
  return { kind, label, subtitle, count: entries.length, rangeStart, rangeEnd, entries }
}

const juyaIssue: JuyaIssueVm = {
  issueId: '2026-10-01',
  eyebrow: 'AI 早报 · 2026-10-01',
  coverUrl: 'assets/previews/juya-cover-20261001.png',
  coverAlt: 'Google 发布 Gemini 4 Argon',
  leadTitle: 'Google 发布 Gemini 4 Argon',
  issueUrl: 'https://daily.juya.uk',
  stories: juya,
}

const juyaSection = section('juya', 'Juya', '橘鸦 AI 早报', juya)
juyaSection.juyaIssues = [juyaIssue]

const digest: DigestVm = {
  ref: 'd15',
  generatedAt: '2026-10-01T20:04:00',
  itemCount: juya.length + hf.length + github.length,
  sourcesReturned: 3,
  sourcesTotal: 4,
  warnings: [
    {
      source: 'bilibili',
      label: 'Bilibili',
      code: 'timeout',
      message:
        'Request timed out. 0 of 5 items returned; other sources completed normally.',
    },
  ],
  sections: [
    juyaSection,
    section('huggingface', 'Hugging Face', 'Trending models', hf),
    section('github', 'GitHub', 'Trending repositories', github),
  ],
}

const messages: MessageVm[] = [
  {
    id: 1,
    sequence: 1,
    kind: 'user',
    text: 'What shipped in AI models and agent tooling this week? Focus on what I should actually learn from.',
    createdAt: '2026-10-01T20:04:00',
    warnings: [],
  },
  {
    id: 2,
    sequence: 2,
    kind: 'digest',
    text: '',
    createdAt: '2026-10-01T20:04:00',
    digest,
    warnings: digest.warnings,
  },
  {
    id: 3,
    sequence: 3,
    kind: 'user',
    text: 'What is a GGUF quant, and should I care?',
    createdAt: '2026-10-01T20:09:00',
    warnings: [],
  },
  {
    id: 4,
    sequence: 4,
    kind: 'markdown',
    text: [
      '### What a GGUF quant is',
      '',
      'A GGUF file is a **quantized** copy of a model, packed for `llama.cpp` and friends.',
      '',
      '- Lower precision, smaller file',
      '- Runs on CPU or a small GPU',
      '',
      '> Check the base model line in the comparison table before you download.',
    ].join('\n'),
    createdAt: '2026-10-01T20:09:00',
    warnings: [],
  },
]

/**
 * Prototype review toolbar. Review-only, so it lives here rather than in `src/`.
 *
 * Digest reply and Empty conversation have production components today; the other
 * prototype states arrive with T7-T9 and are shown disabled until then.
 */
type PrototypeView = {
  id: string
  label: string
  implemented: boolean
}

const PROTOTYPE_VIEWS: PrototypeView[] = [
  { id: 'digest', label: 'Digest reply', implemented: true },
  { id: 'empty', label: 'Empty conversation', implemented: true },
  { id: 'streaming', label: 'Streaming', implemented: false },
  { id: 'streamtext', label: 'Streaming text', implemented: false },
  { id: 'busy', label: 'Conversation busy', implemented: false },
  { id: 'cancelled', label: 'Cancelled', implemented: false },
  { id: 'reconnecting', label: 'Reconnecting', implemented: false },
  { id: 'nomatch', label: 'No history matches', implemented: false },
  { id: 'validation', label: 'Validation error', implemented: false },
]

function messagesFor(view: string): MessageVm[] {
  return view === 'empty' ? [] : messages
}

/** `?state=empty` still opens the empty conversation, as it did before the toolbar. */
function initialView(): string {
  return new URLSearchParams(window.location.search).get('state') === 'empty' ? 'empty' : 'digest'
}

function PrototypeStateBar(onSelect: (id: string) => void, active: string) {
  return h(
    'div',
    {
      class: 'proto',
      role: 'toolbar',
      'aria-label': 'Prototype states (review only, not part of the product)',
      'data-od-id': 'prototype-state-bar',
    },
    [
      h('span', { class: 'proto-label' }, 'Prototype · state'),
      ...PROTOTYPE_VIEWS.map((view) =>
        h(
          'button',
          {
            type: 'button',
            'data-view': view.id,
            'aria-pressed': String(active === view.id),
            disabled: !view.implemented,
            title: view.implemented ? undefined : 'Added with T7/T8/T9',
            onClick: () => {
              if (view.implemented) {
                onSelect(view.id)
              }
            },
          },
          view.label,
        ),
      ),
    ],
  )
}

createApp({
  setup() {
    const view = ref(initialView())
    return () =>
      h('div', { class: 'compare' }, [
        PrototypeStateBar((next) => {
          view.value = next
        }, view.value),
        h(Thread, { messages: messagesFor(view.value) }),
      ])
  },
}).mount('#app')