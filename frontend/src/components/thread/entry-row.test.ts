import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EntryRow from '@/components/thread/EntryRow.vue'
import { githubEntry, juyaEntry } from '@/components/thread/vm-builders'

describe('EntryRow', () => {
  it('shows rank, title link, source tag, and host', () => {
    const wrapper = mount(EntryRow, { props: { entry: githubEntry() } })

    expect(wrapper.get('.rank').text()).toBe('#1')
    expect(wrapper.get('h4 a').text()).toBe('NVIDIA/OpenShell')
    expect(wrapper.get('h4 a').attributes('href')).toBe('https://github.com/NVIDIA/OpenShell')
    expect(wrapper.get('h4 a').attributes('rel')).toBe('noopener')
    expect(wrapper.get('h4 a').attributes('target')).toBe('_blank')
    expect(wrapper.get('.src-tag').text()).toBe('GitHub')
    expect(wrapper.get('.entry-src').text()).toContain('Rust · 13,659 ★ · +2,503 today')
    expect(wrapper.get('.entry-src .ext').text()).toContain('github.com')
  })

  it('omits a null summary, reason, and caveat instead of labelling them empty', () => {
    const wrapper = mount(EntryRow, {
      props: { entry: githubEntry({ summary: null, whyItMatters: null, caveat: null }) },
    })

    expect(wrapper.findAll('dt')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('Summary')
    expect(wrapper.text()).not.toContain('Why it matters')
  })

  it('labels the fields that are present', () => {
    const wrapper = mount(EntryRow, { props: { entry: githubEntry() } })
    const labels = wrapper.findAll('dt').map((dt) => dt.text())

    expect(labels).toEqual(['Summary', 'Why it matters'])
  })

  it('marks a link as previewable only when the entry has a preview url', () => {
    const withPreview = mount(EntryRow, { props: { entry: githubEntry() } })
    const withoutPreview = mount(EntryRow, {
      props: { entry: githubEntry({ previewUrl: null }) },
    })

    expect(withPreview.get('h4 a').attributes('data-preview')).toBe(
      'https://opengraph.test/openshell.png',
    )
    expect(withoutPreview.get('h4 a').attributes('data-preview')).toBeUndefined()
  })

  it('renders the follow-up action as a button, not a duplicate link', () => {
    const wrapper = mount(EntryRow, { props: { entry: githubEntry() } })

    expect(wrapper.get('.entry-foot button').text()).toBe('Ask a follow-up')
  })

  it('renders blank-line-separated Juya prose as separate paragraphs', () => {
    const wrapper = mount(EntryRow, {
      props: { entry: juyaEntry({ summary: 'First sentence.\n\nSecond paragraph.' }) },
    })

    const paragraphs = wrapper.findAll('.entry-body dd')[0]?.findAll('p') ?? []
    expect(paragraphs.map((paragraph) => paragraph.text())).toEqual([
      'First sentence.',
      'Second paragraph.',
    ])
  })

  it('keeps a single Juya paragraph as one paragraph', () => {
    const wrapper = mount(EntryRow, { props: { entry: juyaEntry() } })

    const paragraphs = wrapper.findAll('.entry-body dd')[0]?.findAll('p') ?? []
    expect(paragraphs.map((paragraph) => paragraph.text())).toEqual([
      'Google released Gemini 4 Argon.',
    ])
  })

  it('never renders Juya prose as markup', () => {
    const wrapper = mount(EntryRow, {
      props: { entry: juyaEntry({ summary: '<script>alert(1)</script> & more' }) },
    })

    expect(wrapper.find('.entry-body script').exists()).toBe(false)
    expect(wrapper.get('.entry-body dd').text()).toContain('<script>alert(1)</script> & more')
  })

  it('labels Juya fields in Chinese and collapses long details', () => {
    const wrapper = mount(EntryRow, {
      props: {
        entry: juyaEntry({
          summary: '第一段。'.repeat(40),
          whyItMatters: '影响。'.repeat(30),
          juya: {
            topic: '要闻',
            originalUrl: null,
            storyNumber: 1,
            background: '背景段落一。\n\n背景段落二。',
          },
        }),
      },
    })

    expect(wrapper.findAll('dt').map((dt) => dt.text())).toEqual(['摘要', '为什么重要'])
    const toggle = wrapper.get('.entry-toggle')
    expect(toggle.text()).toBe('展开详情')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.text()).not.toContain('背景段落一')
  })

  it('expands full text and background with an accessible state', async () => {
    const wrapper = mount(EntryRow, {
      props: {
        entry: juyaEntry({
          summary: '摘要。'.repeat(80),
          juya: {
            topic: '要闻',
            originalUrl: null,
            storyNumber: 1,
            background: '背景段落一。\n\n背景段落二。',
          },
        }),
      },
    })

    const toggle = wrapper.get('.entry-toggle')
    await toggle.trigger('click')

    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(toggle.text()).toBe('收起详情')
    expect(wrapper.findAll('dt').map((dt) => dt.text())).toContain('背景知识')
    expect(wrapper.text()).toContain('背景段落一。')
    expect(wrapper.text()).toContain('背景段落二。')
  })

  it('omits the Juya disclosure when there is nothing more to show', () => {
    const wrapper = mount(EntryRow, {
      props: {
        entry: juyaEntry({
          summary: 'Short summary.',
          whyItMatters: 'Short reason.',
          juya: { topic: '要闻', originalUrl: null, storyNumber: 1, background: null },
        }),
      },
    })

    expect(wrapper.find('.entry-toggle').exists()).toBe(false)
  })

  it('asks a Juya story follow-up with its clean headline', async () => {
    const wrapper = mount(EntryRow, {
      props: { entry: juyaEntry({ title: '有关部门拟增列AI技术' }) },
    })

    await wrapper.get('.entry-foot button').trigger('click')

    expect(wrapper.emitted('followup')).toEqual([['有关部门拟增列AI技术']])
  })

  it('asks the entry title as a follow-up when the action is used', async () => {
    const wrapper = mount(EntryRow, { props: { entry: githubEntry() } })

    await wrapper.get('.entry-foot button').trigger('click')

    expect(wrapper.emitted('followup')).toEqual([['NVIDIA/OpenShell']])
  })
})
