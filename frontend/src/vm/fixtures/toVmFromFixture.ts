import { safeHttpUrl, textOrNull } from '@/vm/entries'
import type { FixtureEntry } from '@/vm/fixtures/prototype'
import type { AvatarVm, EntryVm } from '@/vm/types'

/** Preview assets live beside the app rather than at an absolute url. */
const PREVIEW_BASE = '/demo/previews'
const AVATAR_BASE = '/demo/avatars'

function fixtureAvatar(fixture: FixtureEntry): AvatarVm {
  const mono = textOrNull(fixture.avatar?.mono ?? null)
  if (mono !== null) {
    return { type: 'initials', text: mono, title: 'Personal account' }
  }
  const image = textOrNull(fixture.avatar?.image ?? null)
  if (image !== null) {
    return { type: 'image', src: `${AVATAR_BASE}/${image}`, alt: fixture.title }
  }
  return { type: 'none' }
}

function fixtureHost(url: string | null): string | null {
  if (url === null) {
    return null
  }
  return new URL(url).hostname.replace(/^www\./, '')
}

/**
 * Convert one prototype item into the same `EntryVm` shape `toVm` produces.
 *
 * Fixtures and the visual-compare route only; nothing in the production path calls it.
 */
export function toVmFromFixture(fixture: FixtureEntry): EntryVm {
  const url = safeHttpUrl(fixture.url)
  const vm: EntryVm = {
    key: `${fixture.kind}-${fixture.rank}`,
    kind: fixture.kind,
    rank: fixture.rank,
    title: fixture.title,
    url,
    sourceName: fixture.source ?? fixture.title,
    host: fixtureHost(url),
    summary: textOrNull(fixture.summary ?? null),
    whyItMatters: textOrNull(fixture.why ?? null),
    caveat: null,
    followUp: 'read',
    avatar: fixtureAvatar(fixture),
    previewUrl:
      textOrNull(fixture.preview ?? null) === null
        ? null
        : `${PREVIEW_BASE}/${fixture.preview}`,
  }
  if (fixture.meta !== undefined) {
    vm.meta = fixture.meta
  }
  if (fixture.hf !== undefined) {
    const hf = fixture.hf
    vm.hf = {
      modelId: fixture.title,
      trending: hf.trending === undefined ? null : hf.trending.toLocaleString('en-US'),
      downloads30d:
        hf.downloads30d === undefined ? null : hf.downloads30d.toLocaleString('en-US'),
      likes: hf.likes === undefined ? null : hf.likes.toLocaleString('en-US'),
      pipeline: hf.pipeline ?? null,
      baseModel: hf.baseModel ?? null,
      variants: [],
    }
  }
  if (fixture.kind === 'juya') {
    vm.juya = {
      topic: fixture.topic ?? null,
      originalUrl: url,
      // Prototype fixtures carry a prototype rank and no bulletin number.
      storyNumber: null,
      background: null,
    }
  }
  return vm
}
