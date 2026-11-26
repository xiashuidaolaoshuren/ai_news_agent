import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DigestSection from '@/components/thread/DigestSection.vue'
import { githubEntry, juyaEntry, juyaIssue, sectionVm } from '@/components/thread/vm-builders'

describe('DigestSection language', () => {
  it('counts items in Chinese for a zh-CN section', () => {
    const wrapper = mount(DigestSection, {
      props: {
        section: sectionVm({
          lang: 'zh-CN',
          subtitle: '热门仓库',
          count: 2,
          entries: [githubEntry({ lang: 'zh-CN' }), githubEntry({ lang: 'zh-CN', rank: 2 })],
        }),
        digestId: 15,
      },
    })

    expect(wrapper.get('.section-head .sub').text()).toContain('热门仓库 · 2 项')
    expect(wrapper.get('.section-head .sub').text()).not.toContain('items')
  })

  it('labels the Juya issue lead in Chinese for a zh-CN section', () => {
    const wrapper = mount(DigestSection, {
      props: {
        section: sectionVm({
          kind: 'juya',
          label: 'Juya',
          lang: 'zh-CN',
          subtitle: '橘鸦 AI 早报',
          count: 1,
          entries: [juyaEntry()],
          juyaIssues: [juyaIssue({ leadTitle: '头条标题' })],
        }),
        digestId: 15,
      },
    })

    expect(wrapper.get('[data-od-id="juya-issue-cover"]').text()).toContain('头条')
    expect(wrapper.get('[data-od-id="juya-issue-cover"]').text()).not.toContain('Lead story')
  })
})
