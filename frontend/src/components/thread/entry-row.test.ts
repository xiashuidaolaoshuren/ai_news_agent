import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EntryRow from '@/components/thread/EntryRow.vue'
import { githubEntry } from '@/components/thread/vm-builders'

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

  it('asks the entry title as a follow-up when the action is used', async () => {
    const wrapper = mount(EntryRow, { props: { entry: githubEntry() } })

    await wrapper.get('.entry-foot button').trigger('click')

    expect(wrapper.emitted('followup')).toEqual([['NVIDIA/OpenShell']])
  })
})
