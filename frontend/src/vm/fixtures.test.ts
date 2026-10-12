import { describe, expect, it } from 'vitest'

import type { DigestEntryView } from '@/api/generated/types.gen'
import { toSectionsVm, toVm } from '@/vm'
import {
  GH_FIXTURES,
  HF_FIXTURES,
  HIST_FIXTURES,
  JUYA_FIXTURES,
} from '@/vm/fixtures/prototype'
import { toVmFromFixture } from '@/vm/fixtures/toVmFromFixture'

const SOURCES = import.meta.glob('/src/**/*.{ts,vue}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Source files whose text imports anything under a `fixtures/` folder. */
function fixtureImporters(): string[] {
  return Object.entries(SOURCES)
    .filter(([, text]) => /from\s+['"][^'"]*fixtures\//.test(text))
    .map(([path]) => path)
}

function apiEntry(): DigestEntryView {
  return {
    source_kind: 'zhihu',
    source_id: 'zhihu-1',
    title: 'Why small models are winning',
    source_name: 'Zhihu',
    source_url: 'https://www.zhihu.com/question/123',
    summary: 'A discussion of small model deployments.',
    why_it_matters: 'Cheaper inference changes what is worth building.',
    background_knowledge: 'Background.',
    follow_up_action: 'read',
    confidence_caveat: null,
    display_rank: 3,
  }
}

describe('toVmFromFixture', () => {
  it('produces the same Vm shape as the API mapper for the same kind', () => {
    const juyaApiEntry = {
      ...apiEntry(),
      source_kind: 'juya' as const,
      source_id: 'juya-1',
      title: 'Google 发布 Gemini 4 Argon',
      source_name: 'Juya',
      source_url: 'https://daily.juya.uk',
    }
    const fixtureVm = toVmFromFixture(JUYA_FIXTURES[0]!)
    const apiVm = toSectionsVm([juyaApiEntry])[0]!.entries[0]!

    expect(Object.keys(fixtureVm).sort()).toEqual(Object.keys(apiVm).sort())

    const githubFixtureVm = toVmFromFixture(GH_FIXTURES[0]!)
    const githubApiVm = toVm({ ...apiEntry(), source_kind: 'github', source_id: 'g1' })
    expect(Object.keys(githubFixtureVm).sort()).toEqual(Object.keys(githubApiVm).sort())
  })

  it('keeps the prototype GitHub meta line, preview, and avatar', () => {
    const openShell = GH_FIXTURES[0]!

    const vm = toVmFromFixture(openShell)

    expect(vm.kind).toBe('github')
    expect(vm.rank).toBe(11)
    expect(vm.title).toBe('NVIDIA/OpenShell')
    expect(vm.host).toBe('github.com')
    expect(vm.meta).toBe('Rust · 13,659 ★ · +2,503 today')
    expect(vm.previewUrl).toContain('gh-og-NVIDIA-OpenShell.png')
    expect(vm.avatar.type).toBe('image')
  })

  it('keeps the prototype Juya topic and Hugging Face metrics', () => {
    const juya = toVmFromFixture(JUYA_FIXTURES[0]!)
    expect(juya.kind).toBe('juya')
    expect(juya.juya?.topic).toBe('Headlines')
    expect(juya.title).toBe('Google 发布 Gemini 4 Argon')

    const hf = toVmFromFixture(HF_FIXTURES[0]!)
    expect(hf.kind).toBe('huggingface')
    expect(hf.hf?.modelId).toBe('Edge0/Audio8-ASR-Infinite')
    expect(hf.hf?.downloads30d).toBe('27,228')
    expect(hf.hf?.baseModel).toBeNull()
  })

  it('uses a monospace initials tile when the prototype item has no avatar', () => {
    const gguf = HF_FIXTURES.find((item) => item.avatar?.mono === 'AB')

    const vm = toVmFromFixture(gguf!)

    expect(vm.avatar).toEqual({ type: 'initials', text: 'AB', title: 'Personal account' })
    expect(vm.hf?.baseModel).toBe('Qwen/Qwen-Image-2.1')
  })

  it('converts the history rows to entry fixtures too', () => {
    const vm = toVmFromFixture(HIST_FIXTURES[0]!)
    expect(vm.title).toBe('abenzerps/Qwen-Image-2.1-Uncensored-GGUF')
    expect(vm.host).toBe('huggingface.co')
    expect(vm.summary).toBe(
      'GGUF quant of Qwen-Image-2.1 · trending 816 · 1,303,476 downloads (30 days).',
    )

    const juya = toVmFromFixture(HIST_FIXTURES[2]!)
    expect(juya.juya?.topic).toBe('Headlines')
    expect(juya.sourceName).toBe('2026-10-01')
  })
})

describe('fixture import boundary', () => {
  it('scans real source text for fixtures imports', () => {
    // The test module itself is excluded from an eager raw glob (self-reference), so
    // detection is proved on the fixture adapter, which really does import the data.
    expect(fixtureImporters()).toEqual(['/src/vm/fixtures/toVmFromFixture.ts'])
  })

  it('is imported only by the fixtures folder and by tests', () => {
    const offenders = fixtureImporters()
      .filter((path) => !path.startsWith('/src/vm/fixtures/'))
      .filter((path) => !path.endsWith('.test.ts'))

    expect(offenders).toEqual([])
  })
})
