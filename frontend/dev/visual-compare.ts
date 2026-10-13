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
import { toRequestStateVm, type RequestStateVm } from '@/vm/session'
import {
  toCancelledVm,
  toRunVm,
  type CancelledVm,
  type RunVm,
  type RunVmInput,
} from '@/vm/run'

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
 * Every state the spec's thread table lists now has a production component; the
 * composer states (busy, validation) and the history panel arrive with T8-T9.
 */
type PrototypeView = {
  id: string
  label: string
  implemented: boolean
}

const PROTOTYPE_VIEWS: PrototypeView[] = [
  { id: 'digest', label: 'Digest reply', implemented: true },
  { id: 'empty', label: 'Empty conversation', implemented: true },
  { id: 'streaming', label: 'Streaming', implemented: true },
  { id: 'writing', label: 'Writing digest', implemented: true },
  { id: 'streamtext', label: 'Streaming text', implemented: true },
  { id: 'busy', label: 'Conversation busy', implemented: false },
  { id: 'cancelled', label: 'Cancelled', implemented: true },
  { id: 'cancelledtext', label: 'Cancelled reply', implemented: true },
  { id: 'failed', label: 'Failed', implemented: true },
  { id: 'interrupted', label: 'Interrupted', implemented: true },
  { id: 'reconnecting', label: 'Reconnecting', implemented: true },
  { id: 'reconnected', label: 'Reconnected', implemented: true },
  { id: 'nomatch', label: 'No history matches', implemented: false },
  { id: 'validation', label: 'Validation error', implemented: false },
]

/** The prototype's run state: two sources done, one running, one still queued. */
const RUN_SOURCES = ['juya', 'huggingface', 'github', 'bilibili']

function runInput(overrides: Partial<RunVmInput> = {}): RunVmInput {
  return {
    state: 'streaming',
    progress: [
      {
        stage: 'Done juya: Found 5 juya results.',
        source: 'juya',
        status: 'done',
        count: 5,
        at: '20:14:03',
      },
      {
        stage: 'Done huggingface: Found 5 huggingface results.',
        source: 'huggingface',
        status: 'done',
        count: 5,
        at: '20:14:05',
      },
      { stage: 'Calling github…', source: 'github', status: 'running', count: null, at: null },
    ],
    text: '',
    attempt: 0,
    nextDelayMs: null,
    selectedSources: RUN_SOURCES,
    startedAt: '20:14:01',
    droppedAt: null,
    endedAt: null,
    reconnected: false,
    ...overrides,
  }
}

/** Every source finished, so the card shows the writing phase and the shimmer lines. */
const FINISHED_PROGRESS: RunVmInput['progress'] = [
  {
    stage: 'Done juya: Found 5 juya results.',
    source: 'juya',
    status: 'done',
    count: 5,
    at: '20:14:03',
  },
  {
    stage: 'Done huggingface: Found 5 huggingface results.',
    source: 'huggingface',
    status: 'done',
    count: 5,
    at: '20:14:05',
  },
  {
    stage: 'Done github: Found 5 github results.',
    source: 'github',
    status: 'done',
    count: 5,
    at: '20:14:07',
  },
  {
    stage: 'Tool failed bilibili: collection failed.',
    source: 'bilibili',
    status: 'failed',
    count: null,
    at: '20:14:09',
  },
]

const askMessage: MessageVm = {
  id: 5,
  sequence: 5,
  kind: 'user',
  text: 'Any new speech-recognition models I could run locally?',
  createdAt: '2026-10-01T20:14:00',
  warnings: [],
}

const FOLLOWUP_TEXT = [
  '### What a GGUF quant is',
  '',
  'A GGUF file is a **quantized** copy of a model, packed for `llama.cpp` and friends.',
  '',
  '- Lower precision, smaller file',
  '- Runs on CPU or a small GPU',
].join('\n')

interface ViewState {
  messages: MessageVm[]
  run: RunVm | null
  cancelled: CancelledVm | null
  alert: RequestStateVm | null
}

const NO_STATE: ViewState = { messages: [], run: null, cancelled: null, alert: null }

function stateFor(view: string): ViewState {
  switch (view) {
    case 'empty':
      return NO_STATE
    case 'streaming':
      return { ...NO_STATE, messages: [askMessage], run: toRunVm(runInput()) }
    case 'writing':
      return {
        ...NO_STATE,
        messages: [askMessage],
        run: toRunVm(runInput({ progress: FINISHED_PROGRESS })),
      }
    case 'streamtext':
      return {
        ...NO_STATE,
        messages: [askMessage],
        run: toRunVm(runInput({ progress: [], text: FOLLOWUP_TEXT })),
      }
    case 'reconnecting':
      return {
        ...NO_STATE,
        messages: [askMessage],
        run: toRunVm(
          runInput({ state: 'reconnecting', attempt: 2, nextDelayMs: 6000, droppedAt: '20:14:09' }),
        ),
      }
    case 'reconnected':
      return {
        ...NO_STATE,
        messages: [askMessage],
        run: toRunVm(
          runInput({
            state: 'succeeded',
            reconnected: true,
            droppedAt: '20:14:09',
            progress: FINISHED_PROGRESS,
          }),
        ),
      }
    case 'cancelled':
      return {
        ...NO_STATE,
        messages: [askMessage],
        cancelled: toCancelledVm(runInput({ state: 'cancelled', endedAt: '20:14:07' })),
      }
    case 'cancelledtext':
      return {
        ...NO_STATE,
        messages: [askMessage],
        cancelled: toCancelledVm(
          runInput({ state: 'cancelled', endedAt: '20:14:30', progress: [], text: FOLLOWUP_TEXT }),
        ),
      }
    case 'failed':
      return {
        ...NO_STATE,
        messages: [askMessage],
        alert: toRequestStateVm({
          status: 'failed',
          error_code: 'workflow_error',
          error_message: 'Something went wrong.',
        }),
      }
    case 'interrupted':
      return {
        ...NO_STATE,
        messages: [askMessage],
        alert: toRequestStateVm({ status: 'interrupted', error_code: null, error_message: null }),
      }
    default:
      return { ...NO_STATE, messages }
  }
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
        h(Thread, { ...stateFor(view.value) }),
      ])
  },
}).mount('#app')