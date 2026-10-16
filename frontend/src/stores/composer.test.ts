import { describe, expect, it } from 'vitest'
import { ref, shallowRef } from 'vue'

import type { PostMessageBody, SessionOut, SessionPatch } from '@/api/generated/types.gen'
import type { RequestLifecycle, RequestSnapshot } from '@/api/lifecycle'
import { createComposerController, type ComposerDeps } from '@/stores/composer'
import { COUNT_INVALID, PREFS_FAILED, TEXT_REQUIRED, parseSources } from '@/vm/composer'
import type { SentSourcesInput } from '@/vm/session'

const CATALOG = parseSources({
  defaults: ['juya'],
  sources: [
    { name: 'juya', default: true, opt_in: false },
    { name: 'huggingface', default: false, opt_in: true },
    { name: 'github', default: false, opt_in: true },
    { name: 'zhihu', default: false, opt_in: true },
    { name: 'bilibili', default: false, opt_in: true },
  ],
})

function sessionOut(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: 's1',
    title: null,
    connector_names: null,
    items_per_source: null,
    created_at: '2026-10-01T20:00:00Z',
    updated_at: '2026-10-01T20:04:00Z',
    digest_count: 0,
    active_request_id: null,
    ...overrides,
  }
}

function idleSnapshot(): RequestSnapshot {
  return {
    state: 'idle',
    requestId: null,
    sessionId: null,
    userMessageId: null,
    text: '',
    progress: [],
    digest: null,
    error: null,
    attempt: 0,
    nextDelayMs: null,
    blocked: null,
    terminalStatus: null,
  }
}

interface Harness {
  deps: ComposerDeps
  draft: ReturnType<typeof ref<string>>
  session: ReturnType<typeof shallowRef<SessionOut | null>>
  snapshot: ReturnType<typeof shallowRef<RequestSnapshot>>
  sends: { sessionId: string; body: PostMessageBody }[]
  patches: { sessionId: string; body: SessionPatch }[]
  applied: SessionOut[]
  cancelCount: { value: number }
  patchError: { value: string | null }
  marked: { text: string; sources: SentSourcesInput }[]
}

/** Composer controller wired to spies, so no HTTP layer is involved. */
function makeComposer(overrides: Partial<ComposerDeps> = {}): Harness {
  const draft = ref('')
  const session = shallowRef<SessionOut | null>(sessionOut())
  const snapshot = shallowRef<RequestSnapshot>(idleSnapshot())
  const sends: Harness['sends'] = []
  const patches: Harness['patches'] = []
  const applied: SessionOut[] = []
  const cancelCount = { value: 0 }
  const patchError = { value: null as string | null }
  const marked: Harness['marked'] = []
  let ids = 0

  const lifecycle = {
    get state() {
      return snapshot.value
    },
    async send(sessionId: string, body: PostMessageBody): Promise<void> {
      sends.push({ sessionId, body })
    },
    async cancel(): Promise<void> {
      cancelCount.value += 1
    },
    async resume(): Promise<void> {},
    subscribe(): () => void {
      return () => {}
    },
  } as unknown as RequestLifecycle

  const deps: ComposerDeps = {
    loadSources: async () => CATALOG,
    session: () => session.value,
    draft,
    snapshot: () => snapshot.value,
    lifecycle,
    patchPrefs: async (sessionId, body) => {
      patches.push({ sessionId, body })
      if (patchError.value !== null) {
        throw new Error(patchError.value)
      }
      return sessionOut({
        id: sessionId,
        connector_names: body.connector_names ?? null,
        items_per_source: body.items_per_source ?? null,
      })
    },
    applySession: (next) => {
      applied.push(next)
    },
    runAgain: () => {},
    markUserSent: (text, sources) => {
      marked.push({ text, sources })
    },
    newId: () => {
      ids += 1
      return `req-${ids}`
    },
    ...overrides,
  }

  return {
    deps,
    draft,
    session,
    snapshot,
    sends,
    patches,
    applied,
    cancelCount,
    patchError,
    marked,
  }
}

async function ready(overrides: Partial<ComposerDeps> = {}) {
  const harness = makeComposer(overrides)
  const controller = createComposerController(harness.deps)
  await controller.load()
  return { ...harness, controller }
}

describe('composer send', () => {
  it('reports the failing rule and sends nothing', async () => {
    const { controller, sends, draft } = await ready()
    draft.value = '   '

    expect(await controller.send()).toBe(false)
    expect(controller.vm.value.errors).toEqual({ text: TEXT_REQUIRED })
    expect(sends).toEqual([])
  })

  it('sends the trimmed text with stories mode and a fresh request id', async () => {
    const { controller, sends, draft } = await ready()
    draft.value = '  What shipped this week?  '

    expect(await controller.send()).toBe(true)
    expect(sends).toEqual([
      {
        sessionId: 's1',
        body: {
          content: 'What shipped this week?',
          client_request_id: 'req-1',
          juya_item_mode: 'stories',
        },
      },
    ])
    expect(draft.value).toBe('')
    expect(controller.vm.value.errors).toEqual({})
  })

  it('uses a new client request id for every send', async () => {
    const { controller, sends, draft } = await ready()

    draft.value = 'What shipped this week?'
    await controller.send()
    draft.value = 'And what about agents?'
    await controller.send()

    expect(sends.map((item) => item.body.client_request_id)).toEqual(['req-1', 'req-2'])
  })

  it('hands the sent text and its sources to the thread so its bubble shows at once', async () => {
    const { controller, marked, draft } = await ready()
    await controller.toggleSource('github')
    draft.value = '  What shipped this week?  '

    controller.send()

    expect(marked).toEqual([
      {
        text: 'What shipped this week?',
        sources: { names: ['juya', 'github'], perSource: 5 },
      },
    ])
  })

  it('counts a typed item count among the sent sources', async () => {
    const { controller, marked, draft } = await ready()
    await controller.commitCount('8')
    draft.value = 'What shipped this week?'

    controller.send()

    expect(marked[0]?.sources).toEqual({ names: ['juya'], perSource: 8 })
  })
})

describe('composer source preferences', () => {
  it('patches the session when a source is toggled', async () => {
    const { controller, patches, applied } = await ready()

    await controller.toggleSource('github')

    expect(patches).toEqual([
      {
        sessionId: 's1',
        body: { connector_names: ['juya', 'github'], items_per_source: 5 },
      },
    ])
    expect(applied).toHaveLength(1)
  })

  it('keeps the toggle without patching when it would leave no source', async () => {
    const { controller, patches } = await ready()

    await controller.toggleSource('juya')

    expect(patches).toEqual([])
    expect(controller.vm.value.sources.filter((item) => item.checked)).toEqual([])
  })

  it('keeps the selection and reports the failure when the patch is refused', async () => {
    const { controller, patches, patchError } = await ready()
    patchError.value = 'Refused.'

    await controller.toggleSource('github')

    expect(patches).toHaveLength(1)
    expect(controller.selected.value).toEqual(['juya', 'github'])
    expect(controller.vm.value.errors.prefs).toBe(PREFS_FAILED)
  })
})

describe('composer busy and blocked', () => {
  it('disables the inputs and offers Cancel while a run is active', async () => {
    const { controller, snapshot } = await ready()

    snapshot.value = { ...idleSnapshot(), state: 'streaming', requestId: 'r1' }

    expect(controller.vm.value.busy).toBe(true)
    expect(controller.vm.value.notice).toBe('running')
  })

  it('shows the reconnect notice while polling a dropped stream', async () => {
    const { controller, snapshot } = await ready()

    snapshot.value = { ...idleSnapshot(), state: 'reconnecting', requestId: 'r1', attempt: 2 }

    expect(controller.vm.value.busy).toBe(true)
    expect(controller.vm.value.notice).toBe('reconnecting')
  })

  it('refuses a send during a run, keeps the draft, and shows the blocked notice', async () => {
    const { controller, snapshot, sends, draft } = await ready()
    draft.value = 'What shipped this week?'
    snapshot.value = { ...idleSnapshot(), state: 'streaming', requestId: 'r1' }

    expect(controller.send()).toBe(false)

    expect(sends).toEqual([])
    expect(controller.vm.value.busy).toBe(true)
    expect(controller.vm.value.notice).toBe('blocked')
    expect(draft.value).toBe('What shipped this week?')
  })

  it('keeps the composer usable when the server reports another request', async () => {
    const { controller, snapshot } = await ready()

    snapshot.value = { ...idleSnapshot(), blocked: 'session_busy' }

    expect(controller.vm.value.notice).toBe('blocked')
    expect(controller.vm.value.busy).toBe(false)
  })

  it('clears the blocked notice once the run ends', async () => {
    const { controller, snapshot, draft } = await ready()
    draft.value = 'What shipped this week?'
    snapshot.value = { ...idleSnapshot(), state: 'streaming', requestId: 'r1' }
    controller.send()

    snapshot.value = { ...idleSnapshot(), state: 'succeeded', requestId: 'r1' }

    expect(controller.vm.value.notice).toBe('none')
    expect(controller.vm.value.busy).toBe(false)
  })

  it('cancels the running request', async () => {
    const { controller, snapshot, cancelCount } = await ready()
    snapshot.value = { ...idleSnapshot(), state: 'streaming', requestId: 'r1' }

    await controller.cancel()

    expect(cancelCount.value).toBe(1)
  })
})

describe('composer text field', () => {
  it('takes the typed text and clears the text error once it is filled', async () => {
    const { controller, draft } = await ready()
    controller.send()
    expect(controller.vm.value.errors.text).toBe(TEXT_REQUIRED)

    controller.setText('What shipped this week?')

    expect(draft.value).toBe('What shipped this week?')
    expect(controller.vm.value.errors.text).toBeUndefined()
  })
})

describe('composer prefill', () => {
  it('fills the draft, clears the text error, and asks for focus', async () => {
    const { controller, draft } = await ready()
    draft.value = '   '
    controller.send()

    controller.prefill('Summarize the latest Juya AI 早报 for a beginner')

    expect(draft.value).toBe('Summarize the latest Juya AI 早报 for a beginner')
    expect(controller.vm.value.errors.text).toBeUndefined()
    expect(controller.focusToken.value).toBe(1)
  })

  it('templates the follow-up prompt from an entry title', async () => {
    const { controller, draft } = await ready()

    controller.prefillFollowUp('NVIDIA/OpenShell')

    expect(draft.value).toBe(
      'Tell me more about “NVIDIA/OpenShell”: what it is and how I could try it.',
    )
  })

  it('refills from the last user message on Run again and focuses', async () => {
    const harness = makeComposer()
    const controller = createComposerController({
      ...harness.deps,
      runAgain: () => {
        harness.draft.value = 'What shipped this week?'
      },
    })
    await controller.load()

    controller.runAgain()

    expect(harness.draft.value).toBe('What shipped this week?')
    expect(controller.focusToken.value).toBe(1)
  })
})

describe('composer count preferences', () => {
  it('patches the session when a typed count is committed', async () => {
    const { controller, patches } = await ready()

    await controller.commitCount('8')

    expect(controller.vm.value.count).toBe('8')
    expect(patches).toEqual([
      { sessionId: 's1', body: { connector_names: ['juya'], items_per_source: 8 } },
    ])
  })

  it('reports an unusable count, keeps the raw text, and patches nothing', async () => {
    const { controller, patches } = await ready()

    await controller.commitCount('99')

    expect(patches).toEqual([])
    expect(controller.vm.value.count).toBe('99')
    expect(controller.vm.value.errors.count).toBe(COUNT_INVALID)
  })

  it('clamps a stepper step into 1-20 and clears the count error', async () => {
    const { controller, patches } = await ready()
    await controller.commitCount('99')

    await controller.stepCount(-1)

    expect(controller.vm.value.count).toBe('20')
    expect(controller.vm.value.errors.count).toBeUndefined()
    expect(patches).toEqual([
      { sessionId: 's1', body: { connector_names: ['juya'], items_per_source: 20 } },
    ])
  })
})
