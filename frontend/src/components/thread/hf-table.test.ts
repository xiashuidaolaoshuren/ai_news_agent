import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HfTable from '@/components/thread/HfTable.vue'
import { hfEntry } from '@/components/thread/vm-builders'

const withVariant = hfEntry({
  key: 'hf:2',
  rank: 3,
  title: 'XingChen-AGI/TeleOCR',
  hf: {
    modelId: 'XingChen-AGI/TeleOCR',
    trending: '851',
    downloads30d: '31,584',
    likes: '1,129',
    pipeline: 'image-text-to-text',
    baseModel: 'Qwen/Qwen3-8B',
    variants: [
      {
        sourceId: 'Qwen/Qwen3-8B',
        title: 'Fine-tune of',
        url: 'https://huggingface.co/Qwen/Qwen3-8B',
      },
    ],
  },
})

describe('HfTable', () => {
  it('names the eight comparison columns', () => {
    const wrapper = mount(HfTable, { props: { entries: [hfEntry()] } })
    const headers = wrapper.findAll('thead th').map((th) => th.text())

    expect(headers).toEqual([
      'Rank',
      'Model',
      'Link',
      'Trending',
      '30-day downloads',
      'Likes',
      'Pipeline',
      'Variants',
    ])
  })

  it('renders one row per model with its metrics and pipeline', () => {
    const wrapper = mount(HfTable, { props: { entries: [hfEntry()] } })
    const row = wrapper.get('tbody tr')

    expect(row.text()).toContain('#2')
    expect(row.text()).toContain('Edge0/Audio8-ASR-Infinite')
    expect(row.text()).toContain('1,479')
    expect(row.text()).toContain('27,228')
    expect(row.text()).toContain('1,989')
    expect(row.text()).toContain('automatic-speech-recognition')
    expect(row.get('a.ext').attributes('href')).toBe('https://huggingface.co/Edge0/Audio8-ASR-Infinite')
    expect(row.get('a.ext').attributes('rel')).toBe('noopener')
  })

  it('shows a dash when no base model is declared', () => {
    const wrapper = mount(HfTable, { props: { entries: [hfEntry()] } })

    expect(wrapper.get('tbody tr').text()).toContain('—')
    expect(wrapper.get('tbody tr').text()).not.toContain('Fine-tune of')
  })

  it('shows the base model label and source id for a family variant', () => {
    const wrapper = mount(HfTable, { props: { entries: [withVariant] } })
    const row = wrapper.get('tbody tr')

    expect(row.text()).toContain('Fine-tune of')
    expect(row.text()).toContain('Qwen/Qwen3-8B')
  })

  it('keeps the table note about the dash', () => {
    const wrapper = mount(HfTable, { props: { entries: [hfEntry()] } })

    expect(wrapper.get('.table-note').text()).toContain('—')
  })
})
