import { describe, expect, it } from 'vitest'

import { toCancelledVm, toRunVm, type RunVm, type RunVmInput } from '@/vm/run'

function input(overrides: Partial<RunVmInput> = {}): RunVmInput {
  return {
    state: 'streaming',
    progress: [],
    text: '',
    attempt: 0,
    nextDelayMs: null,
    selectedSources: ['juya', 'github', 'zhihu'],
    startedAt: '20:14:01',
    droppedAt: null,
    endedAt: null,
    reconnected: false,
    ...overrides,
  }
}

/** The mapper returns null for states that show no card; tests here always expect one. */
function run(overrides: Partial<RunVmInput> = {}): RunVm {
  const vm = toRunVm(input(overrides))
  expect(vm).not.toBeNull()
  return vm as RunVm
}

function stepRows(vm: RunVm): [string | null, string, number | null][] {
  return vm.steps.map((step) => [step.source, step.status, step.count])
}

describe('toRunVm per-source steps', () => {
  it('marks one source running then done with its count, leaving the rest queued', () => {
    const running = run({
      progress: [
        { stage: 'Calling github…', source: 'github', status: 'running', count: null },
      ],
    })

    expect(stepRows(running)).toEqual([
      ['juya', 'queued', null],
      ['github', 'run', null],
      ['zhihu', 'queued', null],
    ])
    expect(running.finished).toBe(0)
    expect(running.total).toBe(3)

    const done = run({
      progress: [
        { stage: 'Calling github…', source: 'github', status: 'running', count: null },
        {
          stage: 'Done github: Found 3 github results.',
          source: 'github',
          status: 'done',
          count: 3,
        },
      ],
    })

    expect(stepRows(done)).toEqual([
      ['juya', 'queued', null],
      ['github', 'done', 3],
      ['zhihu', 'queued', null],
    ])
    expect(done.finished).toBe(1)
    expect(done.total).toBe(3)
  })

  it('maps a failed connector to the warn step', () => {
    const vm = run({
      progress: [
        {
          stage: 'Tool failed bilibili: collection failed.',
          source: 'bilibili',
          status: 'failed',
          count: null,
        },
      ],
    })

    expect(stepRows(vm)).toEqual([
      ['juya', 'queued', null],
      ['github', 'queued', null],
      ['zhihu', 'queued', null],
      ['bilibili', 'warn', null],
    ])
    expect(vm.finished).toBe(1)
  })

  it('falls back to the stage line when no event carries structured fields', () => {
    const vm = run({
      progress: [
        { stage: 'Collecting from sources…', source: null, status: null, count: null },
        { stage: 'Ranking candidates…', source: null, status: null, count: null },
      ],
    })

    expect(vm.structured).toBe(false)
    expect(vm.fallbackStage).toBe('Ranking candidates…')
    expect(vm.total).toBe(3)
    expect(vm.finished).toBe(0)
  })

  it('switches to the writing phase once every source has finished', () => {
    const fetching = run({
      progress: [
        { stage: 'Done juya: Found 5 juya results.', source: 'juya', status: 'done', count: 5 },
      ],
    })

    expect(fetching.phase).toBe('fetching')
    expect(fetching.headline).toBe('Researching · 1 of 3 sources')

    const writing = run({
      progress: [
        { stage: 'Done juya: Found 5 juya results.', source: 'juya', status: 'done', count: 5 },
        {
          stage: 'Done github: Found 5 github results.',
          source: 'github',
          status: 'done',
          count: 5,
        },
        {
          stage: 'Tool failed zhihu: collection failed.',
          source: 'zhihu',
          status: 'failed',
          count: null,
        },
      ],
    })

    expect(writing.phase).toBe('writing')
    expect(writing.headline).toBe('Writing digest')
  })

  it('treats delta text with no connector progress as a follow-up run', () => {
    const vm = run({
      progress: [{ stage: 'Parsing request…', source: null, status: null, count: null }],
      text: 'A GGUF file is a quantized copy of a model.',
    })

    expect(vm.mode).toBe('followup')
    expect(vm.streamText).toBe('A GGUF file is a quantized copy of a model.')
  })

  it('maps the reconnect attempt, wait, and drop time into the banner', () => {
    const vm = run({
      state: 'reconnecting',
      progress: [
        { stage: 'Calling juya…', source: 'juya', status: 'running', count: null },
      ],
      attempt: 2,
      nextDelayMs: 4000,
      droppedAt: '20:14:09',
    })

    expect(vm.reconnect).toEqual({
      droppedAt: '20:14:09',
      attempt: 2,
      max: 5,
      nextSeconds: 4,
      ok: false,
    })

    expect(run({ state: 'reconnecting', nextDelayMs: null }).reconnect).toEqual({
      droppedAt: null,
      attempt: 0,
      max: 5,
      nextSeconds: null,
      ok: false,
    })
  })

  it('renders no card for a state that shows none', () => {
    expect(toRunVm(input({ state: 'idle' }))).toBeNull()
    expect(toRunVm(input({ state: 'succeeded' }))).toBeNull()
    expect(toRunVm(input({ state: 'failed' }))).toBeNull()
    expect(toRunVm(input({ state: 'cancelled' }))).toBeNull()
    expect(toRunVm(input({ state: 'streaming' }))).toBeNull()
  })

  it('keeps the card during the reconnected dwell and shows the ok banner', () => {
    const vm = run({
      state: 'succeeded',
      reconnected: true,
      progress: [
        { stage: 'Done juya: Found 5 juya results.', source: 'juya', status: 'done', count: 5 },
      ],
    })

    expect(vm.reconnect?.ok).toBe(true)
  })
})

describe('toRunVm step times', () => {
  it('stamps a source with the clock label of the event that finished it', () => {
    const vm = run({
      progress: [
        {
          stage: 'Calling github…',
          source: 'github',
          status: 'running',
          count: null,
          at: '20:14:03',
        },
        {
          stage: 'Done github: Found 5 github results.',
          source: 'github',
          status: 'done',
          count: 5,
          at: '20:14:05',
        },
      ],
    })

    expect(vm.steps.find((step) => step.source === 'github')?.at).toBe('20:14:05')
    expect(vm.steps.find((step) => step.source === 'juya')?.at).toBeNull()
  })
})

describe('toRunVm source labels', () => {
  it('labels a known connector and keeps an unknown name as its raw text', () => {
    const vm = run({
      selectedSources: ['juya', 'mastodon'],
      progress: [
        { stage: 'Collecting from sources…', source: null, status: null, count: null },
      ],
    })

    expect(vm.steps.map((step) => [step.kind, step.label])).toEqual([
      ['juya', 'Juya'],
      [null, 'mastodon'],
    ])
  })
})

describe('toCancelledVm', () => {
  it('reports how many sources finished on a cancelled digest run', () => {
    const vm = toCancelledVm(
      input({
        state: 'cancelled',
        endedAt: '20:14:07',
        progress: [
          { stage: 'Done juya: Found 5 juya results.', source: 'juya', status: 'done', count: 5 },
          {
            stage: 'Done github: Found 5 github results.',
            source: 'github',
            status: 'done',
            count: 5,
          },
          { stage: 'Calling zhihu…', source: 'zhihu', status: 'running', count: null },
        ],
      }),
    )

    expect(vm).toEqual({ mode: 'digest', at: '20:14:07', done: 2, total: 3 })
  })

  it('leaves the counts unknown when the run never knew its sources', () => {
    const vm = toCancelledVm(
      input({
        state: 'cancelled',
        selectedSources: null,
        progress: [
          { stage: 'Collecting from sources…', source: null, status: null, count: null },
        ],
      }),
    )

    expect(vm).toEqual({ mode: 'digest', at: null, done: null, total: null })
  })

  it('marks a cancelled follow-up as a text reply without source counts', () => {
    const vm = toCancelledVm(
      input({
        state: 'cancelled',
        endedAt: '20:14:30',
        text: 'A GGUF file is a quantized copy of a model.',
      }),
    )

    expect(vm).toEqual({ mode: 'text', at: '20:14:30', done: null, total: null })
  })

  it('has no cancelled reply for a run that did not cancel', () => {
    expect(toCancelledVm(input({ state: 'succeeded' }))).toBeNull()
    expect(toCancelledVm(input({ state: 'streaming' }))).toBeNull()
    expect(toCancelledVm(input({ state: 'failed' }))).toBeNull()
  })
})
