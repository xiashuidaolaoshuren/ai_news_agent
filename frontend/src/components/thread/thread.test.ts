import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import Thread from '@/components/thread/Thread.vue'
import type { DigestView, MessageOut } from '@/api/generated/types.gen'
import { toMessageVm } from '@/vm'

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
})
