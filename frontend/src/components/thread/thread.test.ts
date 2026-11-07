import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import Thread from '@/components/thread/Thread.vue'
import type { DigestView, MessageOut } from '@/api/generated/types.gen'
import { toDigestVm, toMessageVm, toMessages, toSentSourcesVm } from '@/vm'
import { toRunVm } from '@/vm/run'

const GITHUB_ENTRY = {
  source_kind: 'github',
  source_id: 'gh:nvidia-openshell',
  title: 'NVIDIA/OpenShell',
  source_name: 'GitHub',
  source_url: 'https://github.com/NVIDIA/OpenShell',
  summary: 'OpenShell is the safe, private runtime for autonomous AI agents.',
  why_it_matters: 'Sandboxed runtimes are becoming the standard answer for agent commands.',
  display_rank: 1,
  follow_up_action: 'try',
  confidence_caveat: null,
  language: 'Rust',
  stars: 13659,
  stars_today: 2503,
  preview_image_url: 'https://opengraph.test/openshell.png',
  owner: { name: 'NVIDIA', avatar_url: 'https://avatars.test/nvidia.png', type: 'organization' },
}

const DIGEST: DigestView = {
  generated_at: '2026-10-01T20:04:00',
  entries: [GITHUB_ENTRY],
} as unknown as DigestView

const WARNING = {
  connector: 'bilibili',
  code: 'timeout',
  message: 'Request timed out. 0 of 5 items returned; other sources completed normally.',
}

function assistantMessage(over: Partial<MessageOut> = {}): MessageOut {
  return {
    id: 2,
    session_id: 's1',
    sequence: 2,
    role: 'assistant',
    content: '',
    run_id: 7,
    created_at: '2026-10-01T20:04:00',
    digest_id: 15,
    digest: DIGEST,
    warnings: [WARNING],
    ...over,
  } as MessageOut
}

describe('Thread', () => {
  it('asks before a large Juya request and does not show a digest until Continue', async () => {
    const [user] = toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        role: 'user',
        content: 'Summarize this issue',
        digest: null,
        digest_id: null,
        warnings: [],
        juya_confirmation: {
          story_count: 24,
          issue: '2026-10',
          issue_number: '42',
        },
      }),
    ])
    const wrapper = mount(Thread, { props: { messages: [user!] } })
    const panel = wrapper.get('[data-od-id="juya-all-confirm"]')

    expect(panel.text()).toContain('24 stories')
    expect(panel.text()).toContain('2026-10')
    expect(panel.text()).toContain('42')
    expect(wrapper.find('[data-od-id^="digest-"]').exists()).toBe(false)

    await wrapper.get('[data-od-id="juya-confirm-continue"]').trigger('click')
    expect(wrapper.emitted('confirmJuya')).toEqual([[{ messageId: 1, action: 'continue' }]])

    await wrapper.get('[data-od-id="juya-confirm-cancel"]').trigger('click')
    expect(wrapper.emitted('confirmJuya')?.[1]).toEqual([{ messageId: 1, action: 'cancel' }])
  })

  it('shows the loading skeleton instead of the empty conversation while opening', () => {
    const wrapper = mount(Thread, { props: { messages: [], loading: true } })

    expect(wrapper.get('[data-od-id="conversation-loading"]').attributes('aria-label')).toBe(
      'Loading conversation',
    )
    expect(wrapper.find('[data-od-id="empty-conversation"]').exists()).toBe(false)
  })

  it('offers a retry when the conversation failed to load', async () => {
    const wrapper = mount(Thread, {
      props: { messages: [], loadError: 'backend down' },
    })

    expect(wrapper.get('[data-od-id="conversation-load-failed"]').text()).toContain(
      'Couldn’t load this conversation.',
    )
    expect(wrapper.find('[data-od-id="empty-conversation"]').exists()).toBe(false)

    await wrapper.get('[data-od-id="retry-load"]').trigger('click')

    expect(wrapper.emitted('retryLoad')).toHaveLength(1)
  })

  it('suggests up to three other sources for a finished empty collect', async () => {
    const [user, noResults] = toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        role: 'user',
        content: 'What shipped in speech models?',
        digest: null,
        digest_id: null,
        warnings: [],
        request: {
          sources: ['github'],
          per_source: 5,
          timeframe: 'past week',
          topics: ['speech models'],
          language: 'en',
          audience: null,
        },
      }),
      assistantMessage({
        id: 2,
        sequence: 2,
        content: '',
        digest: { generated_at: '2026-10-01T20:04:00', entries: [] } as DigestView,
        warnings: [],
        collection_outcome: 'no_eligible',
      }),
    ])
    const wrapper = mount(Thread, {
      props: {
        messages: [user!, noResults!],
        catalog: [
          { name: 'github', label: 'GitHub', kind: 'github' },
          { name: 'juya', label: 'Juya', kind: 'juya' },
          { name: 'huggingface', label: 'Hugging Face', kind: 'huggingface' },
          { name: 'zhihu', label: 'Zhihu', kind: 'zhihu' },
          { name: 'bilibili', label: 'Bilibili', kind: 'bilibili' },
        ],
      },
    })

    const block = wrapper.get('[data-od-id="no-eligible-results"]')
    expect(block.text()).toContain('speech models')
    expect(block.text()).toContain('past week')
    const tries = block.findAll('[data-od-id^="try-"]')
    expect(tries).toHaveLength(3)
    expect(tries.map((button) => button.attributes('data-od-id'))).not.toContain('try-github')

    await tries[0]!.trigger('click')

    expect(wrapper.emitted('repeat')?.[0]?.[0]).toMatchObject({
      userMessageId: 1,
      text: 'What shipped in speech models?',
      replaceSource: 'juya',
    })
  })

  it('names the source that failed to collect instead of calling it no results', async () => {
    const [, failed] = toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        role: 'user',
        content: 'What shipped in speech models?',
        digest: null,
        digest_id: null,
        warnings: [],
        request: {
          sources: ['github'],
          per_source: 5,
          timeframe: null,
          topics: [],
          language: null,
          audience: null,
        },
      }),
      assistantMessage({
        id: 2,
        sequence: 2,
        content: '',
        digest: { generated_at: '2026-10-01T20:04:00', entries: [] } as DigestView,
        warnings: [
          { connector: 'github', code: 'search_failed', message: 'GitHub search returned 503.' },
        ],
        collection_outcome: 'failed',
      }),
    ])
    const wrapper = mount(Thread, { props: { messages: [failed!] } })

    const alert = wrapper.get('[data-od-id="collection-failed"]')
    expect(alert.text()).toContain('Couldn’t collect from GitHub.')
    expect(alert.text()).toContain('GitHub search returned 503.')
    expect(alert.text()).not.toContain('No eligible results')

    await wrapper.get('[data-od-id="retry-collection"]').trigger('click')

    expect(wrapper.emitted('repeat')?.[0]?.[0]).toMatchObject({
      userMessageId: 1,
      text: 'What shipped in speech models?',
    })
    expect(wrapper.emitted('repeat')?.[0]?.[0]).not.toHaveProperty('replaceSource')
  })

  it('renders a user message as a bubble with no agent label', () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [
          toMessageVm(
            assistantMessage({
              id: 1,
              role: 'user',
              content: 'What shipped this week?',
              digest: null,
              digest_id: null,
              warnings: [],
            }),
          ),
        ],
      },
    })

    expect(wrapper.get('.msg-user .bubble').text()).toBe('What shipped this week?')
    expect(wrapper.find('.ai-label').exists()).toBe(false)
  })

  it('labels an assistant reply with the agent name and clock time', () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [
          toMessageVm(
            assistantMessage({ content: '## Heading', digest: null, digest_id: null, warnings: [] }),
          ),
        ],
      },
    })

    expect(wrapper.get('.ai-label').text()).toContain('Agent')
    expect(wrapper.get('.ai-label').text()).toContain('20:04')
  })

  it('sanitizes the markdown of a plain assistant reply', () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [
          toMessageVm(
            assistantMessage({
              content: '### Safe\n\n<script>alert(1)</script>\n\n[docs](https://example.test/d)',
              digest: null,
              digest_id: null,
              warnings: [],
            }),
          ),
        ],
      },
    })
    const reply = wrapper.get('.md')

    expect(reply.get('h3').text()).toBe('Safe')
    expect(reply.find('script').exists()).toBe(false)
    expect(reply.get('a').attributes('rel')).toContain('noopener')
  })

  it('renders a reloaded digest exactly like the live one', () => {
    // The live `digest` event carries the same digest and warnings but no content.
    const live = mount(Thread, { props: { messages: [toMessageVm(assistantMessage())] } })
    const reloaded = mount(Thread, {
      props: {
        messages: [toMessageVm(assistantMessage({ content: 'Digest generated.' }))],
      },
    })

    expect(live.get('.ref').text()).toBe('d15')
    expect(live.findAll('[role="alert"]')).toHaveLength(1)
    expect(reloaded.html()).toBe(live.html())
  })

  it('shows the empty conversation state with three suggestions', async () => {
    const wrapper = mount(Thread, { props: { messages: [] } })

    expect(wrapper.get('.empty h2').text()).toBe('Start a digest')
    const suggestions = wrapper.findAll('.suggest button')

    expect(suggestions).toHaveLength(3)

    await suggestions[0]!.trigger('click')

    expect(wrapper.emitted('suggest')).toEqual([
      ['What shipped in open-weight models this week?'],
    ])
  })

  it('shows no suggestions once the conversation has messages', () => {
    const wrapper = mount(Thread, {
      props: { messages: [toMessageVm(assistantMessage({ digest: null, digest_id: null, warnings: [] }))] },
    })

    expect(wrapper.find('.empty').exists()).toBe(false)
  })

  it('renders the digest a run has streamed but not yet persisted', () => {
    const run = toRunVm({
      state: 'streaming',
      progress: [{ stage: 'Calling github…', source: 'github', status: 'done', count: 3 }],
      text: '',
      attempt: 0,
      nextDelayMs: null,
      selectedSources: ['github'],
      startedAt: '20:14:01',
      droppedAt: null,
      endedAt: null,
      reconnected: false,
      reconnectLeaving: false,
      holding: false,
    })
    const wrapper = mount(Thread, {
      props: {
        messages: [],
        run,
        liveDigest: toDigestVm({ digest: DIGEST, digestId: 15 }),
      },
    })

    // The digest event replaces the progress card, as the spec requires.
    expect(wrapper.get('.live-slot .digest-reply .ref').text()).toBe('d15')
    expect(wrapper.find('[data-od-id="streaming-progress"]').exists()).toBe(false)
    expect(wrapper.find('.empty').exists()).toBe(false)
  })

  it('shows the source chips on a question sent in this page session', () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [
          {
            ...toMessageVm(
              assistantMessage({
                id: 1,
                role: 'user',
                content: 'What shipped this week?',
                digest: null,
                digest_id: null,
                warnings: [],
              }),
            ),
            chips: toSentSourcesVm({ names: ['juya', 'github'], perSource: 5 }),
          },
        ],
      },
    })

    const chips = wrapper.get('.msg-user .req-meta')

    expect(chips.text()).toContain('Juya')
    expect(chips.text()).toContain('GitHub')
    expect(chips.text()).toContain('5/source')
  })

  it('leaves a question with no chips alone', () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [
          toMessageVm(
            assistantMessage({
              id: 1,
              role: 'user',
              content: 'What shipped this week?',
              digest: null,
              digest_id: null,
              warnings: [],
            }),
          ),
        ],
      },
    })

    expect(wrapper.find('.msg-user .req-meta').exists()).toBe(false)
  })

  it('offers earlier messages while the transcript is paged', async () => {
    const wrapper = mount(Thread, {
      props: { messages: [], canLoadOlder: true },
    })

    await wrapper.get('[data-od-id="load-older"]').trigger('click')

    expect(wrapper.emitted('loadOlder')).toHaveLength(1)
  })

  it('has no earlier-messages control for a complete transcript', () => {
    const wrapper = mount(Thread, { props: { messages: [] } })

    expect(wrapper.find('[data-od-id="load-older"]').exists()).toBe(false)
  })

  it('renders a persisted failure as the danger alert', () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [
          toMessageVm(
            assistantMessage({
              content: 'Digest generation failed.',
              digest: null,
              digest_id: null,
              warnings: [],
            }),
          ),
        ],
      },
    })

    expect(wrapper.get('[data-od-id="failed-reply"]').text()).toContain(
      'Digest generation failed.',
    )
  })

  it('offers to keep polling only while the outcome is still unknown', async () => {
    const wrapper = mount(Thread, {
      props: {
        messages: [],
        alert: {
          kind: 'failed',
          message: 'The request failed.',
          canRunAgain: true,
          canRetryPoll: true,
        },
      },
    })

    const buttons = wrapper.findAll('.alert button')
    expect(buttons.map((button) => button.text())).toEqual(['Run again', 'Keep polling'])

    await buttons[1]!.trigger('click')

    expect(wrapper.emitted('retryPoll')).toHaveLength(1)

    const known = mount(Thread, {
      props: {
        messages: [],
        alert: { kind: 'failed', message: 'Digest generation failed.', canRunAgain: true },
      },
    })

    expect(known.text()).not.toContain('Keep polling')
  })
})
