import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, onTestFinished, vi } from 'vitest'

import Thread from '@/components/thread/Thread.vue'
import type { DigestView, MessageOut } from '@/api/generated/types.gen'
import type { OlderPageResult } from '@/stores/thread'
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
  it('links an assistant reply to its reference as the prototype does', () => {
    const [user, reply] = toMessages(
      [
        assistantMessage({
          id: 1,
          sequence: 1,
          role: 'user',
          content: 'What is this?',
          digest: null,
          digest_id: null,
          warnings: [],
          followup_target: { digest_id: 12, display_rank: 3 },
        }),
        assistantMessage({
          id: 2,
          sequence: 2,
          content: 'It is a runtime.',
          digest: null,
          digest_id: null,
          warnings: [],
          created_at: '2026-10-01T20:14:00',
        }),
      ],
    )
    const wrapper = mount(Thread, { props: { messages: [user!, reply!] } })

    const link = wrapper.get('[data-od-id="reply-ref-link"]')
    expect(link.element.tagName).toBe('A')
    expect(link.attributes('aria-label')).toBe('In reply to d12 #3')
    expect(link.attributes('data-ref')).toBe('d12-3')

    // The clock comes before the link, as in the prototype's label.
    const label = wrapper.get('.msg-ai .ai-label')
    expect(label.element.firstElementChild?.textContent).toBe('Agent')
    const parts = Array.from(label.element.children).map((child) => child.className)
    expect(parts).toEqual(['', 'mono', 're'])
  })

  it('shows a pending confirmation as an agent message, naming the issue publisher', () => {
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
    expect(panel.element.closest('.msg-ai')).not.toBeNull()
    expect(panel.element.closest('.msg-user')).toBeNull()
    expect(panel.text()).toContain('from 橘鸦 AI 早报')
  })

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
        // The visible catalog: a hidden source is already absent from it.
        catalog: [
          { name: 'github', label: 'GitHub', kind: 'github' },
          { name: 'juya', label: 'Juya', kind: 'juya' },
          { name: 'huggingface', label: 'Hugging Face', kind: 'huggingface' },
          { name: 'zhihu', label: 'Zhihu', kind: 'zhihu' },
        ],
      },
    })

    const block = wrapper.get('[data-od-id="no-eligible-results"]')
    expect(block.text()).toContain('speech models')
    expect(block.text()).toContain('past week')
    const tries = block.findAll('[data-od-id^="try-"]')
    expect(tries).toHaveLength(3)
    expect(tries.map((button) => button.attributes('data-od-id'))).not.toContain('try-github')
    expect(block.find('[data-od-id="try-bilibili"]').exists()).toBe(false)

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

  it('ends a collection reason with one full stop before the no-results sentence', () => {
    const failedWith = (message: string) => {
      const [, failed] = toMessages([
        assistantMessage({
          id: 1,
          sequence: 1,
          role: 'user',
          content: 'New models today?',
          digest: null,
          digest_id: null,
          warnings: [],
          request: {
            sources: ['openrouter'],
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
          warnings: [{ connector: 'openrouter', code: 'request_failed', message }],
          collection_outcome: 'failed',
        }),
      ])
      return mount(Thread, { props: { messages: [failed!] } }).get(
        '[data-od-id="collection-failed"]',
      ).text()
    }

    expect(failedWith('OpenRouter models request failed')).toContain(
      'OpenRouter models request failed. No stories were checked',
    )
    expect(failedWith('GitHub search returned 503.')).toContain(
      'GitHub search returned 503. No stories were checked',
    )
    expect(failedWith('GitHub search returned 503.')).not.toContain('..')
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

  it('shows the empty conversation state with four suggestions', async () => {
    const wrapper = mount(Thread, { props: { messages: [] } })

    expect(wrapper.get('.empty h2').text()).toBe('Start a digest')
    const suggestions = wrapper.findAll('.suggest button')

    expect(suggestions).toHaveLength(4)

    await suggestions[0]!.trigger('click')

    expect(wrapper.emitted('suggest')).toEqual([["Digest today's AI news"]])
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

  it('puts the reference chip above the bubble and the source chips below it', () => {
    const [user] = toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        role: 'user',
        content: 'What is this?',
        digest: null,
        digest_id: null,
        warnings: [],
        followup_target: { digest_id: 12, display_rank: 3 },
      }),
    ])
    const wrapper = mount(Thread, {
      props: {
        messages: [
          {
            ...user!,
            chips: toSentSourcesVm({ names: ['juya'], perSource: 5 }),
          },
        ],
      },
    })

    const order = Array.from(wrapper.get('.msg-user').element.children).map(
      (child) =>
        child.classList.contains('ref-chip')
          ? 'chip'
          : child.classList.contains('bubble')
            ? 'bubble'
            : 'sources',
    )
    expect(order).toEqual(['chip', 'bubble', 'sources'])
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

  it('offers to keep polling only while the outcome is still unknown', async () => {    const wrapper = mount(Thread, {
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

  it('offers the deep-dive reply the same Related chip its digest row shows', async () => {
    const relatedDigest = {
      generated_at: '2026-10-01T20:04:00',
      entries: [{ ...GITHUB_ENTRY, related_display_ranks: [5] }],
    } as unknown as DigestView
    const messages = toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        content: '',
        digest: relatedDigest,
        digest_id: 15,
        warnings: [],
      }),
      assistantMessage({
        id: 2,
        sequence: 2,
        role: 'user',
        content: 'Deep dive on OpenShell',
        digest: null,
        digest_id: null,
        warnings: [],
        followup_action: 'deep_dive',
        followup_target: { digest_id: 15, display_rank: 1 },
      }),
      assistantMessage({
        id: 3,
        sequence: 3,
        content: 'It is a sandboxed runtime.',
        digest: null,
        digest_id: null,
        warnings: [],
      }),
    ])
    const wrapper = mount(Thread, { props: { messages } })

    // One chip on the digest row, one on the deep-dive card.
    expect(wrapper.findAll('[data-od-id="related-5"]')).toHaveLength(1)
    const card = wrapper.findAll('[data-od-id="related-reply-5"]')
    expect(card).toHaveLength(1)
    expect(card[0]!.text()).toBe('Related: #5')
    expect(card[0]!.attributes('aria-label')).toBe(
      'Related: entry #5 names the same model',
    )

    await card[0]!.trigger('click')

    // The chip navigates the thread; it never sends a turn.
    expect(wrapper.emitted('ask')).toBeUndefined()
    expect(wrapper.emitted('deepdive')).toBeUndefined()
    expect(wrapper.emitted('repeat')).toBeUndefined()
  })

  function deepDive(relatedRanks: number[]) {
    return toMessages([
      assistantMessage({
        id: 2,
        role: 'user',
        content: 'Deep dive on OpenShell',
        digest: null,
        digest_id: null,
        warnings: [],
        followup_action: 'deep_dive',
        followup_target: { digest_id: 15, display_rank: 1 },
      }),
      assistantMessage({
        id: 3,
        sequence: 3,
        content: 'It is a sandboxed runtime.',
        digest: null,
        digest_id: null,
        warnings: [],
        followup_related_display_ranks: relatedRanks,
      }),
    ])
  }

  function earlierDigest(ranks = [1]) {
    return toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        digest: {
          ...DIGEST,
          entries: ranks.map((rank) => ({
            ...GITHUB_ENTRY,
            source_id: `entry-${rank}`,
            display_rank: rank,
          })),
        } as unknown as DigestView,
        warnings: [],
      }),
    ])[0]!
  }

  function observeScroll() {
    const targets: HTMLElement[] = []
    const prototype = HTMLElement.prototype
    const original = Object.getOwnPropertyDescriptor(prototype, 'scrollIntoView')
    Object.defineProperty(prototype, 'scrollIntoView', {
      configurable: true,
      value(this: HTMLElement) { targets.push(this) },
    })
    onTestFinished(() => {
      if (original === undefined) {
        Reflect.deleteProperty(prototype, 'scrollIntoView')
      } else {
        Object.defineProperty(prototype, 'scrollIntoView', original)
      }
    })
    return targets
  }

  function pendingPage() {
    let resolve!: (outcome: OlderPageResult) => void
    const promise = new Promise<OlderPageResult>((done) => { resolve = done })
    return { promise, resolve }
  }

  function loaded(requestedCursor: string, nextCursor: string | null): OlderPageResult {
    return { status: 'loaded', requestedCursor, nextCursor }
  }

  const jumpStatus = '[data-od-id="related-jump-status"]'
  const relatedChip = (rank: number) => `[data-od-id="related-reply-${rank}"]`

  it('jumps a deep-dive Related chip to the digest row, not the reply link', async () => {
    const scrolled = observeScroll()
    const loadOlder = vi.fn()
    // Put the same-key reply link first so a generic ref lookup would choose it.
    const messages = [...deepDive([1]), earlierDigest()]
    const wrapper = mount(Thread, { props: { messages, loadOlder } })

    await wrapper.get(relatedChip(1)).trigger('click')

    const row = wrapper.get('.entry[data-ref="d15-1"]')
    expect(scrolled).toEqual([row.element])
    expect(row.classes()).toContain('hl')
    expect(loadOlder).not.toHaveBeenCalled()
    expect(wrapper.emitted('ask')).toBeUndefined()
    expect(wrapper.emitted('deepdive')).toBeUndefined()
  })

  it('loads earlier pages for an off-page Related target and flashes it once rendered', async () => {
    const scrolled = observeScroll()
    const firstPage = pendingPage()
    const secondPage = pendingPage()
    const loadOlder = vi.fn<() => Promise<OlderPageResult>>()
      .mockReturnValueOnce(firstPage.promise)
      .mockReturnValueOnce(secondPage.promise)
    const messages = deepDive([2])
    const wrapper = mount(Thread, { props: { messages, loadOlder } })
    loadOlder.mockImplementationOnce(async () => {
      await wrapper.setProps({ messages: [earlierDigest([1, 2]), ...messages] })
      return loaded('older-3', null)
    })

    await wrapper.get(relatedChip(2)).trigger('click')
    expect(loadOlder).toHaveBeenCalledTimes(1)
    expect(wrapper.get(jumpStatus).text()).toContain('Loading earlier messages')
    expect(scrolled).toEqual([])

    firstPage.resolve(loaded('older-1', 'older-2'))
    await flushPromises()
    expect(loadOlder).toHaveBeenCalledTimes(2)
    expect(scrolled).toEqual([])

    secondPage.resolve(loaded('older-2', 'older-3'))
    await flushPromises()
    expect(loadOlder).toHaveBeenCalledTimes(3)
    const row = wrapper.get('.entry[data-ref="d15-2"]')
    expect(scrolled).toEqual([row.element])
    expect(row.classes()).toContain('hl')
    expect(wrapper.emitted('ask')).toBeUndefined()
    expect(wrapper.emitted('deepdive')).toBeUndefined()
  })

  it('shows localized paging status only on the deep-dive card whose chip was clicked', async () => {
    const first = deepDive([2])[1]!
    const second = {
      ...first,
      id: first.id + 1,
      replyRef: { digestId: 16, rank: 1, title: 'Second', lang: 'zh-CN' as const },
    }
    const page = pendingPage()
    const loadOlder = vi.fn(() => page.promise)
    const wrapper = mount(Thread, { props: { messages: [first, second], loadOlder } })
    const cards = wrapper.findAll('.row-related')

    await cards[1]!.get(relatedChip(2)).trigger('click')
    expect(cards[1]!.get(jumpStatus).text()).toContain('正在加载')
    expect(cards[0]!.find(jumpStatus).exists()).toBe(false)
    page.resolve({ status: 'exhausted' })
    await flushPromises()
    expect(cards[1]!.get(jumpStatus).text()).toContain('当前对话')
  })

  it('says the related entry is unavailable when the transcript ends without it', async () => {
    const loadOlder = vi.fn<() => Promise<OlderPageResult>>()
      .mockResolvedValueOnce(loaded('older-1', null))
      .mockResolvedValueOnce({ status: 'exhausted' })
    const wrapper = mount(Thread, { props: { messages: deepDive([2]), loadOlder } })

    await wrapper.get(relatedChip(2)).trigger('click')
    await flushPromises()

    expect(wrapper.get(jumpStatus).text()).toContain('not in this conversation')
    expect(loadOlder).toHaveBeenCalledTimes(1)
  })

  it('offers another try after an older page fails, then jumps on retry', async () => {
    const scrolled = observeScroll()
    const retry = pendingPage()
    const loadOlder = vi.fn<() => Promise<OlderPageResult>>()
      .mockResolvedValueOnce({ status: 'failed' })
      .mockReturnValueOnce(retry.promise)
    const messages = deepDive([1])
    const wrapper = mount(Thread, { props: { messages, loadOlder } })
    const chip = wrapper.get(relatedChip(1))

    await chip.trigger('click')
    await flushPromises()
    expect(wrapper.get(jumpStatus).text()).toContain('Try again')
    expect(loadOlder).toHaveBeenCalledTimes(1)

    await chip.trigger('click')
    expect(loadOlder).toHaveBeenCalledTimes(2)
    expect(scrolled).toEqual([])
    await wrapper.setProps({ messages: [earlierDigest(), ...messages] })
    retry.resolve(loaded('older-1', null))
    await flushPromises()

    expect(scrolled).toEqual([wrapper.get('.entry[data-ref="d15-1"]').element])
  })

  it('stops when an older page repeats a cursor instead of requesting it again', async () => {
    const loadOlder = vi.fn<() => Promise<OlderPageResult>>()
      .mockResolvedValueOnce(loaded('older-1', 'older-2'))
      .mockResolvedValueOnce(loaded('older-2', 'older-1'))
      .mockResolvedValue({ status: 'exhausted' })
    const wrapper = mount(Thread, { props: { messages: deepDive([2]), loadOlder } })

    await wrapper.get(relatedChip(2)).trigger('click')
    await flushPromises()

    expect(wrapper.get(jumpStatus).text()).toContain('Try again')
    expect(loadOlder).toHaveBeenCalledTimes(2)
  })

  it('lets the latest Related click finish without feedback or scrolling from the old one', async () => {
    const scrolled = observeScroll()
    const oldPage = pendingPage()
    const newPage = pendingPage()
    const loadOlder = vi.fn<() => Promise<OlderPageResult>>()
      .mockReturnValueOnce(oldPage.promise)
      .mockReturnValueOnce(newPage.promise)
    const messages = deepDive([1, 2])
    const wrapper = mount(Thread, { props: { messages, loadOlder } })

    await wrapper.get(relatedChip(1)).trigger('click')
    await wrapper.get(relatedChip(2)).trigger('click')
    oldPage.resolve(loaded('older-1', 'older-2'))
    await flushPromises()
    expect(wrapper.get(jumpStatus).text()).toContain('Loading earlier')
    expect(scrolled).toEqual([])

    await wrapper.setProps({ messages: [earlierDigest([1, 2]), ...messages] })
    newPage.resolve(loaded('older-2', null))
    await flushPromises()
    expect(loadOlder).toHaveBeenCalledTimes(2)
    expect(scrolled).toEqual([wrapper.get('.entry[data-ref="d15-2"]').element])
    expect(wrapper.find(jumpStatus).exists()).toBe(false)
  })

  it.each(['transcript replacement', 'unmount'])('drops an in-flight jump on %s', async (reason) => {
    const page = pendingPage()
    const loadOlder = vi.fn(() => page.promise)
    const wrapper = mount(Thread, {
      props: { messages: deepDive([2]), transcriptGeneration: 1, loadOlder },
    })
    await wrapper.get(relatedChip(2)).trigger('click')
    if (reason === 'unmount') {
      wrapper.unmount()
    } else {
      await wrapper.setProps({ transcriptGeneration: 2 })
      expect(wrapper.find(jumpStatus).exists()).toBe(false)
    }
    page.resolve(loaded('older-1', 'older-2'))
    await flushPromises()
    expect(loadOlder).toHaveBeenCalledTimes(1)
  })

  it('shows no Related chip on a deep-dive reply whose entry has none', () => {
    const messages = toMessages([
      assistantMessage({
        id: 1,
        sequence: 1,
        content: '',
        digest: DIGEST,
        digest_id: 15,
        warnings: [],
      }),
      assistantMessage({
        id: 2,
        sequence: 2,
        role: 'user',
        content: 'Deep dive on OpenShell',
        digest: null,
        digest_id: null,
        warnings: [],
        followup_action: 'deep_dive',
        followup_target: { digest_id: 15, display_rank: 1 },
      }),
      assistantMessage({
        id: 3,
        sequence: 3,
        content: 'It is a sandboxed runtime.',
        digest: null,
        digest_id: null,
        warnings: [],
      }),
    ])
    const wrapper = mount(Thread, { props: { messages } })

    expect(wrapper.find('[data-od-id^="related-reply-"]').exists()).toBe(false)
  })
})
