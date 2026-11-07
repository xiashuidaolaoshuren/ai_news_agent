import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SettingsDialog from '@/components/settings/SettingsDialog.vue'
import type { SourceProfileVm } from '@/vm/settings'

const PROFILES: SourceProfileVm[] = [
  { name: 'juya', hidden: false, itemCount: 5 },
  {
    name: 'github',
    hidden: false,
    itemCount: 5,
    keywords: [],
    minStars: 0,
    language: null,
  },
  { name: 'huggingface', hidden: false, itemCount: 5, pipelineTag: null },
  { name: 'openrouter', hidden: false, itemCount: 5, freeOnly: false },
  { name: 'zhihu', hidden: false, itemCount: 5 },
  { name: 'bilibili', hidden: true },
]

function mountDialog() {
  return mount(SettingsDialog, {
    props: {
      vm: {
        open: true,
        tab: 'sources',
        language: 'source_default',
        profiles: PROFILES,
        fieldErrors: {},
        saved: false,
        loadError: null,
        focus: null,
      },
    },
  })
}

describe('SettingsDialog', () => {
  it('lists every source on the Sources tab, including hidden Bilibili', () => {
    const wrapper = mountDialog()

    expect(wrapper.get('[data-od-id="settings-dialog"]').attributes('role')).toBe('dialog')
    expect(wrapper.get('[data-od-id="settings-tab-sources"]').attributes('aria-selected')).toBe(
      'true',
    )
    for (const name of ['juya', 'github', 'huggingface', 'openrouter', 'zhihu', 'bilibili']) {
      expect(wrapper.find(`[data-od-id="settings-source-${name}"]`).exists()).toBe(true)
    }
    expect(wrapper.get('[data-od-id="settings-source-bilibili"]').text()).toContain(
      'Hidden from source selection',
    )
    expect(wrapper.find('[data-od-id="settings-output-language"]').exists()).toBe(true)
  })

  it('asks to save the current sources', async () => {
    const wrapper = mountDialog()

    await wrapper.get('[data-od-id="save-sources"]').trigger('click')

    expect(wrapper.emitted('save')).toHaveLength(1)
  })
})
