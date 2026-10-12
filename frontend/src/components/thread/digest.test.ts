import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DigestReply from '@/components/thread/DigestReply.vue'
import { digestVm, githubEntry, juyaEntry, juyaIssue, sectionVm, warningVm } from '@/components/thread/vm-builders'

describe('DigestReply', () => {
  it('shows the digest reference, time, item count, and source tally', () => {
    const wrapper = mount(DigestReply, { props: { digest: digestVm() } })
    const head = wrapper.get('.digest-head')

    expect(head.get('h2').text()).toBe('Digest')
    expect(head.get('.ref').text()).toBe('d15')
    expect(head.text()).toContain('Oct 1, 2026 · 20:04')
    expect(head.text()).toContain('5 items')
    expect(head.text()).toContain('2 of 3 sources returned results')
  })

  it('omits the reference badge when the digest has no id', () => {
    const wrapper = mount(DigestReply, { props: { digest: digestVm({ ref: null }) } })

    expect(wrapper.find('.ref').exists()).toBe(false)
  })

  it('renders one alert per connector warning', () => {
    const wrapper = mount(DigestReply, {
      props: {
        digest: digestVm({
          warnings: [
            warningVm(),
            warningVm({
              source: 'bilibili',
              label: 'Bilibili',
              code: 'timeout',
              message: 'Request timed out. 0 of 5 items returned.',
            }),
          ],
        }),
      },
    })
    const alerts = wrapper.findAll('[role="alert"]')

    expect(alerts).toHaveLength(2)
    expect(alerts[0]!.text()).toContain('GitHub connector:')
    expect(alerts[0]!.text()).toContain('other sources completed normally')
    expect(alerts[1]!.text()).toContain('Bilibili connector:')
  })

  it('renders one section per digest section with its head range', () => {
    const wrapper = mount(DigestReply, {
      props: { digest: digestVm({ sections: [sectionVm({ count: 5, rangeStart: 1, rangeEnd: 5 })] }) },
    })

    expect(wrapper.findAll('.section')).toHaveLength(1)
    expect(wrapper.get('.section-head').text()).toContain('GitHub')
    expect(wrapper.get('.section-head').text()).toContain('Trending repositories')
    expect(wrapper.get('.section-head').text()).toContain('5 items')
    expect(wrapper.get('.section-head').text()).toContain('#1–5')
  })

  it('lists the section entries in order under the section head', () => {
    const wrapper = mount(DigestReply, {
      props: {
        digest: digestVm({
          sections: [
            sectionVm({
              count: 2,
              rangeStart: 1,
              rangeEnd: 2,
              entries: [
                githubEntry({ rank: 1 }),
                githubEntry({ key: 'github:2', rank: 2, title: 'mattpocock/skills' }),
              ],
            }),
          ],
        }),
      },
    })
    const rows = wrapper.findAll('.entries .entry')

    expect(rows).toHaveLength(2)
    expect(rows[0]!.get('.rank').text()).toBe('#1')
    expect(rows[1]!.get('.rank').text()).toBe('#2')
  })

  it('groups Juya stories under one issue cover with the lead title as alt', () => {
    const stories = [
      juyaEntry({ rank: 1 }),
      juyaEntry({ key: 'juya:2', rank: 2, title: '哔哩哔哩发布并开源 Index Translate' }),
    ]
    const wrapper = mount(DigestReply, {
      props: {
        digest: digestVm({
          itemCount: 2,
          sections: [
            sectionVm({
              kind: 'juya',
              label: 'Juya',
              subtitle: '橘鸦 AI 早报',
              count: 2,
              rangeStart: 1,
              rangeEnd: 2,
              entries: stories,
              juyaIssues: [juyaIssue({ stories })],
            }),
          ],
        }),
      },
    })

    expect(wrapper.findAll('.issue')).toHaveLength(1)
    expect(wrapper.get('.issue .eyebrow').text()).toBe('AI 早报 · 2026-10-01')
    expect(wrapper.get('.issue img').attributes('src')).toBe(
      'https://cdn.test/juya-cover-20261001.png',
    )
    expect(wrapper.get('.issue img').attributes('alt')).toBe('Google 发布 Gemini 4 Argon')
    expect(wrapper.get('.issue .ext').attributes('href')).toBe('https://daily.juya.uk')
    expect(wrapper.findAll('.entries .entry')).toHaveLength(2)
    expect(wrapper.get('.issue-meta').text()).toContain('Lead story')
  })

  it('omits the Lead story label when the issue has no lead title', () => {
    const stories = [juyaEntry({ rank: 1 })]
    const wrapper = mount(DigestReply, {
      props: {
        digest: digestVm({
          sections: [
            sectionVm({
              kind: 'juya',
              label: 'Juya',
              subtitle: '橘鸦 AI 早报',
              count: 1,
              rangeStart: 1,
              rangeEnd: 1,
              entries: stories,
              juyaIssues: [juyaIssue({ leadTitle: null, coverAlt: null, stories })],
            }),
          ],
        }),
      },
    })

    expect(wrapper.get('.issue-meta').text()).not.toContain('Lead story')
  })

  it('shows the story topic and the original link on a Juya story row', () => {    const story = juyaEntry({
      rank: 1,
      juya: { topic: 'Headlines', originalUrl: 'https://original.test/story-1' },
    })
    const wrapper = mount(DigestReply, {
      props: {
        digest: digestVm({
          sections: [
            sectionVm({
              kind: 'juya',
              label: 'Juya',
              subtitle: '橘鸦 AI 早报',
              count: 1,
              rangeStart: 1,
              rangeEnd: 1,
              entries: [story],
              juyaIssues: [juyaIssue({ stories: [story] })],
            }),
          ],
        }),
      },
    })
    const row = wrapper.get('.entries .entry')

    expect(row.get('.entry-src').text()).toContain('Headlines')
    expect(row.get('.entry-src .ext').attributes('href')).toBe('https://original.test/story-1')
  })

  it('bubbles a follow-up from an entry row up to the digest reply', async () => {
    const wrapper = mount(DigestReply, { props: { digest: digestVm() } })

    await wrapper.get('.entry-foot button').trigger('click')

    expect(wrapper.emitted('followup')).toEqual([['NVIDIA/OpenShell']])
  })
})
