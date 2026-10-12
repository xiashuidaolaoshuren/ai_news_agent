import { describe, expect, it } from 'vitest'

import type {
  DigestEntryView,
  GitHubDigestEntryView,
  HuggingFaceDigestEntryView,
} from '@/api/generated/types.gen'
import { safeHttpUrl, toVm } from '@/vm'

function zhihuEntry(overrides: Partial<DigestEntryView> = {}): DigestEntryView {
  return {
    source_kind: 'zhihu',
    source_id: 'zhihu-1',
    title: 'Why small models are winning',
    source_name: 'Zhihu',
    source_url: 'https://www.zhihu.com/question/123',
    summary: 'A discussion of small model deployments.',
    why_it_matters: 'Cheaper inference changes what is worth building.',
    background_knowledge: 'Small models trade accuracy for cost.',
    follow_up_action: 'read',
    confidence_caveat: 'Single thread.',
    display_rank: 3,
    ...overrides,
  }
}

describe('toVm', () => {
  it('maps the common entry fields and derives the host', () => {
    const vm = toVm(zhihuEntry())

    expect(vm).toMatchObject({
      kind: 'zhihu',
      rank: 3,
      title: 'Why small models are winning',
      url: 'https://www.zhihu.com/question/123',
      sourceName: 'Zhihu',
      host: 'zhihu.com',
      summary: 'A discussion of small model deployments.',
      whyItMatters: 'Cheaper inference changes what is worth building.',
      caveat: 'Single thread.',
      followUp: 'read',
    })
    expect(vm.key).toBe('zhihu-1')
  })

  it('renders blank optional text as null instead of an empty label', () => {
    const vm = toVm(
      zhihuEntry({ summary: '   ', why_it_matters: '', confidence_caveat: null }),
    )

    expect(vm.summary).toBeNull()
    expect(vm.whyItMatters).toBeNull()
    expect(vm.caveat).toBeNull()
  })

  it('carries no kind-specific extras for a generic entry', () => {
    const vm = toVm(zhihuEntry())

    expect(vm.meta).toBeUndefined()
    expect(vm.hf).toBeUndefined()
    expect(vm.juya).toBeUndefined()
    expect(vm.previewUrl).toBeNull()
  })
})

describe('safeHttpUrl', () => {
  it('keeps http and https urls unchanged', () => {
    expect(safeHttpUrl('https://github.com/NVIDIA/OpenShell')).toBe(
      'https://github.com/NVIDIA/OpenShell',
    )
    expect(safeHttpUrl('http://127.0.0.1:8765/api/v1/health')).toBe(
      'http://127.0.0.1:8765/api/v1/health',
    )
  })

  it('rejects non-http schemes, relative paths, blanks, and junk', () => {
    for (const url of [
      'javascript:alert(1)',
      'data:text/html;base64,PHNjcmlwdD4=',
      'file:///etc/passwd',
      '/sessions/s1',
      'github.com/NVIDIA/OpenShell',
      '',
      '   ',
      'not a url',
      null,
      undefined,
    ]) {
      expect(safeHttpUrl(url)).toBeNull()
    }
  })
})

describe('toVm url safety', () => {
  it('drops a non-http source url and its host', () => {
    const vm = toVm(zhihuEntry({ source_url: 'javascript:alert(1)' }))

    expect(vm.url).toBeNull()
    expect(vm.host).toBeNull()
  })

  it('drops a relative source url but keeps the entry', () => {
    const vm = toVm(zhihuEntry({ source_url: '/local/path' }))

    expect(vm.url).toBeNull()
    expect(vm.host).toBeNull()
    expect(vm.title).toBe('Why small models are winning')
  })
})

describe('avatar choice', () => {
  function githubEntry(overrides: Partial<GitHubDigestEntryView> = {}): GitHubDigestEntryView {
    return {
      source_kind: 'github',
      source_id: 'NVIDIA/OpenShell',
      title: 'NVIDIA/OpenShell',
      source_name: 'GitHub',
      source_url: 'https://github.com/NVIDIA/OpenShell',
      summary: 'A safe runtime for agents.',
      why_it_matters: 'Sandboxed runtimes are becoming standard.',
      background_knowledge: 'Agents need isolation.',
      follow_up_action: 'read',
      display_rank: 1,
      stars: 13659,
      ...overrides,
    }
  }

  it('uses the image when the owner has an avatar url', () => {
    const vm = toVm(
      githubEntry({
        owner: {
          name: 'NVIDIA',
          avatar_url: 'https://avatars.example/nvidia.png',
          type: 'organisation',
        },
      }),
    )

    expect(vm.avatar).toEqual({
      type: 'image',
      src: 'https://avatars.example/nvidia.png',
      alt: 'NVIDIA',
    })
  })

  it('falls back to an initials tile for a person without an image', () => {
    const vm = toVm(githubEntry({ owner: { name: 'abenzerps', type: 'person' } }))

    expect(vm.avatar).toEqual({ type: 'initials', text: 'AB', title: 'Personal account' })
  })

  it('falls back to a neutral tile for an organisation without an image', () => {
    const vm = toVm(githubEntry({ owner: { name: 'NVIDIA', type: 'organisation' } }))

    expect(vm.avatar).toEqual({ type: 'neutral' })
  })

  it('has no avatar when the entry has no owner', () => {
    const vm = toVm(githubEntry({ owner: null }))

    expect(vm.avatar).toEqual({ type: 'none' })
  })

  it('never uses a non-http avatar url as an image', () => {
    const vm = toVm(
      githubEntry({
        owner: { name: 'abenzerps', avatar_url: 'javascript:alert(1)', type: 'person' },
      }),
    )

    expect(vm.avatar).toEqual({ type: 'initials', text: 'AB', title: 'Personal account' })
  })
})

describe('GitHub projection', () => {
  function githubEntry(overrides: Partial<GitHubDigestEntryView> = {}): GitHubDigestEntryView {
    return {
      source_kind: 'github',
      source_id: 'NVIDIA/OpenShell',
      title: 'NVIDIA/OpenShell',
      source_name: 'GitHub',
      source_url: 'https://github.com/NVIDIA/OpenShell',
      summary: 'A safe runtime for agents.',
      why_it_matters: 'Sandboxed runtimes are becoming standard.',
      background_knowledge: 'Agents need isolation.',
      follow_up_action: 'read',
      display_rank: 1,
      ...overrides,
    }
  }

  it('builds the meta line from language, stars, and stars today', () => {
    const vm = toVm(
      githubEntry({
        language: 'Rust',
        stars: 13659,
        stars_today: 2503,
        preview_image_url: 'https://opengraph.githubassets.com/1/NVIDIA/OpenShell',
      }),
    )

    expect(vm.meta).toBe('Rust · 13,659 ★ · +2,503 today')
    expect(vm.previewUrl).toBe('https://opengraph.githubassets.com/1/NVIDIA/OpenShell')
  })

  it('drops each null meta segment independently', () => {
    expect(toVm(githubEntry({ language: 'Rust', stars: 13659 })).meta).toBe(
      'Rust · 13,659 ★',
    )
    expect(toVm(githubEntry({ stars: 149759, stars_today: 1179 })).meta).toBe(
      '149,759 ★ · +1,179 today',
    )
    expect(toVm(githubEntry({ language: 'Shell', stars_today: 888 })).meta).toBe(
      'Shell · +888 today',
    )
    expect(toVm(githubEntry()).meta).toBeUndefined()
  })

  it('never keeps a non-http preview url', () => {
    const vm = toVm(githubEntry({ preview_image_url: 'javascript:alert(1)' }))

    expect(vm.previewUrl).toBeNull()
    expect(vm.meta).toBeUndefined()
  })
})

describe('Hugging Face projection', () => {
  function hfEntry(
    overrides: Partial<HuggingFaceDigestEntryView> = {},
  ): HuggingFaceDigestEntryView {
    return {
      source_kind: 'huggingface',
      source_id: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      title: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      source_name: 'Hugging Face',
      source_url: 'https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      summary: 'A community GGUF quant.',
      why_it_matters: 'Local image generation without a hosted API.',
      background_knowledge: 'GGUF is the llama.cpp format.',
      follow_up_action: 'try',
      display_rank: 9,
      trending_score: 816,
      downloads_30d: 1303476,
      likes: 2626,
      pipeline_tag: 'text-to-image',
      base_model: 'Qwen/Qwen-Image-2.1',
      ...overrides,
    }
  }

  it('projects the comparison-table metrics with thousands separators', () => {
    const vm = toVm(hfEntry())

    expect(vm.hf).toEqual({
      modelId: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      trending: '816',
      downloads30d: '1,303,476',
      likes: '2,626',
      pipeline: 'text-to-image',
      baseModel: 'Qwen/Qwen-Image-2.1',
      variants: [],
    })
    expect(vm.meta).toBeUndefined()
  })

  it('omits metrics that are absent instead of showing zero', () => {
    const vm = toVm(
      hfEntry({
        trending_score: null,
        downloads_30d: null,
        likes: null,
        pipeline_tag: null,
        base_model: null,
      }),
    )

    expect(vm.hf).toEqual({
      modelId: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
      trending: null,
      downloads30d: null,
      likes: null,
      pipeline: null,
      baseModel: null,
      variants: [],
    })
  })

  it('keeps family variants with a safe url and drops unsafe ones', () => {
    const vm = toVm(
      hfEntry({
        family_variants: [
          {
            source_id: 'Qwen/Qwen3-8B',
            title: 'Qwen/Qwen3-8B',
            url: 'https://huggingface.co/Qwen/Qwen3-8B',
            downloads_30d: 2720,
            likes: 583,
          },
          { source_id: 'bad/model', title: 'bad/model', url: 'javascript:alert(1)' },
        ],
      }),
    )

    expect(vm.hf?.variants).toEqual([
      { sourceId: 'Qwen/Qwen3-8B', title: 'Qwen/Qwen3-8B', url: 'https://huggingface.co/Qwen/Qwen3-8B' },
      { sourceId: 'bad/model', title: 'bad/model', url: null },
    ])
  })
})
