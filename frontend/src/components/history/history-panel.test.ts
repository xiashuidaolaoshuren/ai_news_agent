import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { HistorySearchResultOut } from '@/api/generated/types.gen'
import HistoryPanel from '@/components/history/HistoryPanel.vue'
import { githubEntry } from '@/components/thread/vm-builders'
import {
  EMPTY_HISTORY_FILTERS,
  toHistoryMatchVm,
  toHistoryPanelVm,
  type HistoryPanelVm,
} from '@/vm'

const MATCH = {
  ref: { token: 'd15r3', digest_id: 15, run_id: 4, entry_id: 3, rank: 3 },
  generated_at: '2026-10-01T20:04:00',
  source_kind: 'github' as const,
  title: 'NVIDIA/OpenShell',
  url: 'https://github.com/NVIDIA/OpenShell',
  excerpt: 'OpenShell is the safe, private runtime for autonomous AI agents.',
  score: 9,
  topics: ['Agent tooling'],
}

const RESULT: HistorySearchResultOut = {
  matches: [MATCH],
  caveats: [],
  archive_truncated: false,
  scanned_count: 1,
}

/** An opened result with one match, resolved to an entry or falling back to markdown. */
function openedVm(
  options: { url?: string | null; withEntry?: boolean } = {},
): HistoryPanelVm {
  const match = toHistoryMatchVm({
    ...MATCH,
    url: options.url === undefined ? MATCH.url : (options.url as string),
  })
  return toHistoryPanelVm({
    filters: { ...EMPTY_HISTORY_FILTERS, text: 'openshell' },
    status: 'ready',
    result: RESULT,
    error: null,
    opened: {
      match,
      status: 'ready',
      item: {
        token: match.token,
        entry: options.withEntry === true ? githubEntry() : null,
        markdown: 'A saved reply.',
      },
      error: null,
    },
  })
}

function opened(wrapper: ReturnType<typeof mount>) {
  return wrapper.get('[data-od-id="history-opened-result"]')
}

describe('HistoryPanel opened result', () => {
  it('shows the topic and offers the source page and Ask in chat', async () => {
    const wrapper = mount(HistoryPanel, { props: { vm: openedVm() } })
    const block = opened(wrapper)

    expect(block.text()).toContain('Agent tooling')

    const link = block.get('a.btn')
    expect(link.attributes('href')).toBe('https://github.com/NVIDIA/OpenShell')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    expect(link.text()).toContain('Open source page')

    const ask = block.findAll('button').find((button) => button.text().includes('Ask in chat'))
    expect(ask).toBeDefined()

    await ask?.trigger('click')

    expect(wrapper.emitted('ask')).toEqual([['NVIDIA/OpenShell']])
  })

  it('keeps the actions when the saved entry resolved', () => {
    const wrapper = mount(HistoryPanel, { props: { vm: openedVm({ withEntry: true }) } })
    const block = opened(wrapper)

    expect(block.find('.entries').exists()).toBe(true)
    expect(block.get('a.btn').text()).toContain('Open source page')
    expect(block.text()).toContain('Ask in chat')
  })

  it('leaves the source page out when the match has no usable url', () => {
    const wrapper = mount(HistoryPanel, {
      props: { vm: openedVm({ url: 'javascript:alert(1)' }) },
    })
    const block = opened(wrapper)

    expect(block.find('a.btn').exists()).toBe(false)
    expect(block.text()).toContain('Ask in chat')
  })
})
