/** View-model types. API types stop at the `toVm` boundary. */

export type EntryKind = 'github' | 'huggingface' | 'juya' | 'zhihu' | 'bilibili'

export type FollowUpKind = 'read' | 'watch' | 'try' | 'build'

/** Avatar presentation choice for an entry title row. */
export type AvatarVm =
  | { type: 'image'; src: string; alt: string }
  | { type: 'initials'; text: string; title: string }
  | { type: 'neutral' }
  | { type: 'none' }

/** One row of the Hugging Face comparison table. */
export interface HfVariantVm {
  sourceId: string
  title: string
  url: string | null
}

export interface HfVm {
  modelId: string
  trending: string | null
  downloads30d: string | null
  likes: string | null
  pipeline: string | null
  baseModel: string | null
  variants: HfVariantVm[]
}

/** Juya-specific presentation data. */
export interface JuyaVm {
  topic: string | null
  originalUrl: string | null
  /** The story's number in its bulletin, which is not its digest rank. */
  storyNumber: number | null
}

export interface EntryVm {
  key: string
  kind: EntryKind
  rank: number
  title: string
  url: string | null
  sourceName: string
  host: string | null
  summary: string | null
  whyItMatters: string | null
  caveat: string | null
  followUp: FollowUpKind
  avatar: AvatarVm
  previewUrl: string | null
  meta?: string
  hf?: HfVm
  juya?: JuyaVm
}
