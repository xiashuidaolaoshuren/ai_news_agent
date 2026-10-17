import type {
  DigestView,
  GitHubDigestEntryView,
  HuggingFaceDigestEntryView,
  JuyaDigestEntryView,
  PublisherOwnerView,
} from '@/api/generated/types.gen'
import type { AvatarVm, EntryKind, EntryVm, HfVm } from '@/vm/types'

/** Any digest entry the API can send, including the kind-specific views. */
export type ApiDigestEntry = NonNullable<DigestView['entries']>[number]

/**
 * The source discriminator.
 *
 * Kind-specific views declare `source_kind` optional in the generated types because
 * the backend gives it a default, but FastAPI always serializes it. A missing value
 * therefore falls back to the generic entry view, which carries no kind extras.
 */
export function entryKind(api: ApiDigestEntry): EntryKind {
  return api.source_kind ?? 'zhihu'
}

/** Trimmed text, or null when empty so the UI omits the label entirely. */
export function textOrNull(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Absolute http(s) url, or null. Blocks `javascript:`, `data:`, and relative paths. */
export function safeHttpUrl(url: string | null | undefined): string | null {
  const value = textOrNull(url)
  if (value === null) {
    return null
  }
  try {
    const parsed = new URL(value)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null
    }
    return value
  } catch {
    return null
  }
}

const DEMO_ASSET_PATH = /^\/(avatars|previews)\/[^/]+$/

/**
 * Map prototype-db image urls onto same-origin `/demo/...` assets.
 *
 * Live connector urls pass through unchanged.
 */
export function resolveDemoAsset(url: string | null | undefined): string | null {
  const safe = safeHttpUrl(url)
  if (safe === null) {
    return null
  }
  let parsed: URL
  try {
    parsed = new URL(safe)
  } catch {
    return null
  }
  if (parsed.hostname !== 'demo-assets.local') {
    return safe
  }
  if (safe.includes('/../') || safe.includes('/./')) {
    return null
  }
  if (!DEMO_ASSET_PATH.test(parsed.pathname)) {
    return null
  }
  return new URL(`/demo${parsed.pathname}`, window.location.origin).href
}

/** Host name for a link label, without the `www.` prefix. */
export function hostOf(url: string | null): string | null {
  const safe = safeHttpUrl(url)
  if (safe === null) {
    return null
  }
  return new URL(safe).hostname.replace(/^www\./, '')
}

const PERSONAL_ACCOUNT_TITLE = 'Personal account'

/** First two alphanumeric characters of a name, for the monospace initials tile. */
export function initialsOf(name: string): string {
  return name.replace(/[^a-zA-Z0-9]/g, '').slice(0, 2).toUpperCase()
}

/** Avatar choice: image, person initials tile, neutral organisation tile, or none. */
export function avatarFor(owner: PublisherOwnerView | null | undefined): AvatarVm {
  if (owner === null || owner === undefined) {
    return { type: 'none' }
  }
  const image = resolveDemoAsset(owner.avatar_url)
  if (image !== null) {
    return { type: 'image', src: image, alt: owner.name }
  }
  if (owner.type === 'person') {
    return { type: 'initials', text: initialsOf(owner.name), title: PERSONAL_ACCOUNT_TITLE }
  }
  return { type: 'neutral' }
}

/** `1,234` style formatting used by every numeric label. */
export function formatCount(value: number): string {
  return value.toLocaleString('en-US')
}

/** Formatted metric, or null when the API omitted it. */
export function metricText(value: number | null | undefined): string | null {
  return typeof value === 'number' ? formatCount(value) : null
}

/** GitHub meta line: `language · stars ★ · +N today`, omitting null segments. */
export function githubMeta(entry: GitHubDigestEntryView): string | undefined {
  const parts: string[] = []
  const language = textOrNull(entry.language ?? null)
  if (language !== null) {
    parts.push(language)
  }
  if (typeof entry.stars === 'number') {
    parts.push(`${formatCount(entry.stars)} ★`)
  }
  if (typeof entry.stars_today === 'number') {
    parts.push(`+${formatCount(entry.stars_today)} today`)
  }
  return parts.length === 0 ? undefined : parts.join(' · ')
}

/** Hugging Face comparison-table data. `modelId` is the entry title (the repo id). */
export function huggingFaceVm(entry: HuggingFaceDigestEntryView): HfVm {
  const variants = (entry.family_variants ?? []).map((variant) => ({
    sourceId: variant.source_id,
    title: variant.title,
    url: safeHttpUrl(variant.url),
  }))
  return {
    modelId: entry.title,
    trending: metricText(entry.trending_score),
    downloads30d: metricText(entry.downloads_30d),
    likes: metricText(entry.likes),
    pipeline: textOrNull(entry.pipeline_tag),
    baseModel: textOrNull(entry.base_model),
    variants,
  }
}

/** Project one API digest entry onto its view-model. */
export function toVm(api: ApiDigestEntry): EntryVm {
  const url = safeHttpUrl(api.source_url)
  const kind = entryKind(api)
  const owner = (api as { owner?: PublisherOwnerView | null }).owner
  const vm: EntryVm = {
    key: api.source_id,
    kind,
    rank: api.display_rank,
    title: api.title,
    url,
    sourceName: api.source_name,
    host: hostOf(url),
    summary: textOrNull(api.summary),
    whyItMatters: textOrNull(api.why_it_matters),
    caveat: textOrNull(api.confidence_caveat),
    followUp: api.follow_up_action,
    avatar: avatarFor(owner),
    previewUrl: null,
  }
  if (kind === 'github') {
    const github = api as GitHubDigestEntryView
    vm.meta = githubMeta(github)
    vm.previewUrl = resolveDemoAsset(github.preview_image_url)
  }
  if (kind === 'huggingface') {
    vm.hf = huggingFaceVm(api as HuggingFaceDigestEntryView)
  }
  return vm
}

/**
 * Entry with any kind-specific presentation attached.
 *
 * `rank` stays the digest-wide `display_rank`: a Juya bulletin number is local
 * to its issue and can skip (#1, #2, #4), so it is kept beside the rank.
 */
export function toEntryVm(api: ApiDigestEntry): EntryVm {
  const vm = toVm(api)
  if (vm.kind === 'juya') {
    const juya = api as JuyaDigestEntryView
    const storyNumber = juya.story?.number
    vm.juya = {
      topic: textOrNull(juya.story?.section ?? null),
      originalUrl: safeHttpUrl(juya.story?.original_url),
      storyNumber: typeof storyNumber === 'number' ? storyNumber : null,
      background: textOrNull(juya.background_knowledge),
    }
  }
  return vm
}
