/** One source profile from `GET /api/v1/settings/sources`, in UI field names. */
export type SourceProfileVm =
  | { name: 'juya'; hidden: boolean; itemCount: number | 'all' }
  | {
      name: 'github'
      hidden: boolean
      itemCount: number
      keywords: string[]
      minStars: number
      language: string | null
    }
  | {
      name: 'huggingface'
      hidden: boolean
      itemCount: number
      pipelineTag: string | null
    }
  | { name: 'openrouter'; hidden: boolean; itemCount: number; freeOnly: boolean }
  | { name: 'zhihu'; hidden: boolean; itemCount: number }
  | { name: 'bilibili'; hidden: boolean }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function mapProfile(item: Record<string, unknown>): SourceProfileVm {
  const hidden = item.hidden === true
  switch (item.name) {
    case 'juya':
      return { name: 'juya', hidden, itemCount: item.item_count as number | 'all' }
    case 'github':
      return {
        name: 'github',
        hidden,
        itemCount: item.item_count as number,
        keywords: item.keywords as string[],
        minStars: item.min_stars as number,
        language: item.language as string | null,
      }
    case 'huggingface':
      return {
        name: 'huggingface',
        hidden,
        itemCount: item.item_count as number,
        pipelineTag: item.pipeline_tag as string | null,
      }
    case 'openrouter':
      return {
        name: 'openrouter',
        hidden,
        itemCount: item.item_count as number,
        freeOnly: item.free_only as boolean,
      }
    case 'zhihu':
      return { name: 'zhihu', hidden, itemCount: item.item_count as number }
    case 'bilibili':
      return { name: 'bilibili', hidden }
    default:
      throw new Error(`unknown source ${String(item.name)}`)
  }
}

/** Read source profiles out of the untyped settings list. */
export function toSourceProfilesVm(raw: unknown): SourceProfileVm[] {
  if (!isRecord(raw) || !Array.isArray(raw.sources)) {
    throw new Error('settings response is not a profile list')
  }
  return raw.sources.map((item) => {
    if (!isRecord(item) || typeof item.name !== 'string') {
      throw new Error('settings response is not a profile list')
    }
    return mapProfile(item)
  })
}
