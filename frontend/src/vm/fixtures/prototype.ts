import type { EntryKind } from '@/vm/types'

/**
 * Prototype items converted to fixtures for visual comparison only.
 *
 * Values are copied verbatim from the approved prototype so a rendered fixture can be
 * diffed against it. No production path imports this module.
 */
export interface FixtureAvatar {
  image?: string
  mono?: string
}

export interface FixtureEntry {
  kind: EntryKind
  rank: number
  title: string
  url: string
  source?: string
  summary?: string
  why?: string
  meta?: string
  preview?: string
  avatar?: FixtureAvatar
  topic?: string
  /** Hugging Face only. */
  hf?: {
    trending?: number
    downloads30d?: number
    likes?: number
    pipeline?: string
    baseModel?: string
  }
}

/** Juya AI 早报 2026-10-01. */
export const JUYA_FIXTURES: FixtureEntry[] = [
  {
    kind: 'juya',
    rank: 1,
    title: 'Google 发布 Gemini 4 Argon',
    url: 'https://daily.juya.uk',
    source: 'AI 早报 2026-10-01',
    topic: 'Headlines',
    summary:
      'Google released Gemini 4 Argon. Lead story and cover of the 10-01 issue.',
    why: 'A new Gemini generation moves the comparison baseline; expect this month’s benchmark claims to cite it.',
  },
  {
    kind: 'juya',
    rank: 2,
    title: '哔哩哔哩发布并开源 Index Translate 多语言翻译模型系列',
    url: 'https://daily.juya.uk',
    source: 'AI 早报 2026-10-01',
    topic: 'Model releases',
    summary:
      'Bilibili released and open-sourced Index Translate, a series of multilingual translation models.',
    why: 'Open translation weights you can run locally and compare against hosted translation APIs.',
  },
  {
    kind: 'juya',
    rank: 3,
    title: '蚂蚁百灵发布 Ling 3.1 flash，开放两周免费体验',
    url: 'https://daily.juya.uk',
    source: 'AI 早报 2026-10-01',
    topic: 'Model releases',
    summary: 'Ant Group’s Ling team released Ling 3.1 flash, with a two-week free trial.',
    why: 'A free window is a low-cost chance to test a fast model on your own prompts.',
  },
  {
    kind: 'juya',
    rank: 4,
    title: 'MiniMax 上线 M Plan 订阅，Token Plan 停止新购',
    url: 'https://daily.juya.uk',
    source: 'AI 早报 2026-10-01',
    topic: 'Industry',
    summary:
      'MiniMax launched an M Plan subscription and stopped selling its Token Plan to new buyers.',
    why: 'If you call MiniMax from your own projects, check how the pricing change affects you.',
  },
  {
    kind: 'juya',
    rank: 5,
    title: 'Space Bunny Alpha 匿名测试期延长至 10 月 5 日',
    url: 'https://daily.juya.uk',
    source: 'AI 早报 2026-10-01',
    topic: 'Model releases',
    summary: 'The anonymous test period for Space Bunny Alpha was extended to October 5.',
    why: 'Anonymous test models often precede a named release; worth trying while the window is open.',
  },
]

/** Hugging Face trending API, 2026-10-01. */
export const HF_FIXTURES: FixtureEntry[] = [
  {
    kind: 'huggingface',
    rank: 6,
    title: 'Edge0/Audio8-ASR-Infinite',
    url: 'https://huggingface.co/Edge0/Audio8-ASR-Infinite',
    avatar: { image: 'hf-Edge0.webp' },
    summary: 'Trending on the Hugging Face Hub.',
    why: 'A fast-moving speech model worth comparing against your current stack.',
    hf: {
      trending: 1479,
      downloads30d: 27228,
      likes: 1989,
      pipeline: 'automatic-speech-recognition',
    },
  },
  {
    kind: 'huggingface',
    rank: 7,
    title: 'convaiinnovations/laya',
    url: 'https://huggingface.co/convaiinnovations/laya',
    avatar: { image: 'hf-convaiinnovations.webp' },
    summary: 'Trending on the Hugging Face Hub.',
    why: 'Useful when you need classification without a hosted API.',
    hf: { trending: 1293, downloads30d: 0, likes: 4739, pipeline: 'text-classification' },
  },
  {
    kind: 'huggingface',
    rank: 8,
    title: 'XingChen-AGI/TeleOCR',
    url: 'https://huggingface.co/XingChen-AGI/TeleOCR',
    avatar: { image: 'hf-XingChen-AGI.webp' },
    summary: 'Trending on the Hugging Face Hub.',
    why: 'Document parsing is a common agent sub-task.',
    hf: {
      trending: 851,
      downloads30d: 31584,
      likes: 1129,
      pipeline: 'image-text-to-text',
    },
  },
  {
    kind: 'huggingface',
    rank: 9,
    title: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
    url: 'https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
    avatar: { mono: 'AB' },
    summary: 'A community GGUF quant of Qwen-Image-2.1.',
    why: 'Quantized weights are the practical way to run image models locally.',
    hf: {
      trending: 816,
      downloads30d: 1303476,
      likes: 2626,
      pipeline: 'text-to-image',
      baseModel: 'Qwen/Qwen-Image-2.1',
    },
  },
  {
    kind: 'huggingface',
    rank: 10,
    title: 'Contrastive-LM/CLM-v0.1-8B',
    url: 'https://huggingface.co/Contrastive-LM/CLM-v0.1-8B',
    avatar: { image: 'hf-Contrastive-LM.webp' },
    summary: 'A fine-tune of Qwen3-8B for ranking.',
    why: 'A concrete example of a small fine-tune on a known base model.',
    hf: {
      trending: 498,
      downloads30d: 2720,
      likes: 583,
      pipeline: 'text-ranking',
      baseModel: 'Qwen/Qwen3-8B',
    },
  },
]

/** GitHub Trending, 2026-10-01. */
export const GH_FIXTURES: FixtureEntry[] = [
  {
    kind: 'github',
    rank: 11,
    title: 'NVIDIA/OpenShell',
    url: 'https://github.com/NVIDIA/OpenShell',
    avatar: { image: 'gh-NVIDIA.png' },
    preview: 'gh-og-NVIDIA-OpenShell.png',
    meta: 'Rust · 13,659 ★ · +2,503 today',
    summary: 'OpenShell is the safe, private runtime for autonomous AI agents.',
    why: 'Sandboxed runtimes are becoming the standard answer to “can I let an agent run commands?”. Worth understanding the model.',
  },
  {
    kind: 'github',
    rank: 12,
    title: 'DietrichGebert/ponytail',
    url: 'https://github.com/DietrichGebert/ponytail',
    avatar: { image: 'gh-DietrichGebert.png' },
    meta: 'JavaScript · 149,759 ★ · +1,179 today',
    summary:
      'Makes your AI agent think like the laziest senior dev in the room. The best code is the code you never wrote.',
    why: 'A compact example of steering agent behaviour with instructions alone, against over-engineering.',
  },
  {
    kind: 'github',
    rank: 13,
    title: 'mattpocock/skills',
    url: 'https://github.com/mattpocock/skills',
    avatar: { image: 'gh-mattpocock.png' },
    preview: 'gh-og-mattpocock-skills.png',
    meta: 'Shell · 273,407 ★ · +888 today',
    summary: 'Skills for Real Engineers. Straight from my .agents directory.',
    why: 'A concrete reference for how to structure reusable agent skill files.',
  },
  {
    kind: 'github',
    rank: 14,
    title: 'mvschwarz/openrig',
    url: 'https://github.com/mvschwarz/openrig',
    avatar: { image: 'gh-mvschwarz.png' },
    meta: 'TypeScript · 3,333 ★ · +640 today',
    summary:
      'Build your own network of agents from Claude Code, Codex and Pi: persistent teams with roles, shared context and owned work.',
    why: 'Shows one practical pattern for long-lived multi-agent teams with shared context.',
  },
  {
    kind: 'github',
    rank: 15,
    title: 'mksglu/context-mode',
    url: 'https://github.com/mksglu/context-mode',
    avatar: { image: 'gh-mksglu.png' },
    meta: 'TypeScript · 24,650 ★ · +357 today',
    summary:
      'Context window optimization for AI coding agents. Sandboxes tool output, persists session memory, routes via MCP + hooks.',
    why: 'Context budgeting is a recurring bottleneck; this is a hands-on way to learn the techniques.',
  },
]

/** Saved digest rows used by the history panel fixture. */
export const HIST_FIXTURES: FixtureEntry[] = [
  {
    kind: 'huggingface',
    rank: 9,
    title: 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
    url: 'https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF',
    source: '2026-10-01',
    topic: 'Model releases',
    summary: 'GGUF quant of Qwen-Image-2.1 · trending 816 · 1,303,476 downloads (30 days).',
  },
  {
    kind: 'github',
    rank: 11,
    title: 'NVIDIA/OpenShell',
    url: 'https://github.com/NVIDIA/OpenShell',
    source: '2026-10-01',
    topic: 'Developer ecosystem',
    summary: 'OpenShell is the safe, private runtime for autonomous AI agents.',
  },
  {
    kind: 'juya',
    rank: 1,
    title: 'Google 发布 Gemini 4 Argon',
    url: 'https://daily.juya.uk',
    source: '2026-10-01',
    topic: 'Headlines',
    summary: 'From AI 早报 2026-10-01, item #1.',
  },
]
