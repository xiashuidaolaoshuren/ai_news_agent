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

/** Every credential the Settings Keys panel can show, in API env-name form. */
export type CredentialId =
  | 'OPENAI_API_KEY'
  | 'OPENAI_BASE_URL'
  | 'OPENAI_MODEL'
  | 'GITHUB_TOKEN'
  | 'HUGGINGFACE_TOKEN'
  | 'ZHIHU_ACCESS_SECRET'
  | 'BILIBILI_SESSDATA'
  | 'BILIBILI_BILI_JCT'
  | 'BILIBILI_BUVID3'

/** Row state: saved in the app, from the environment, not set, or unreadable. */
export type CredentialState = 'app' | 'env' | 'none' | 'bad'

export interface CredentialRowVm {
  status: CredentialState
  last4: string | null
  version: string | null
}

/** Everything the Keys panel renders; no secret ever enters this shape. */
export interface CredentialsVm {
  /** Without the encryption key the backend refuses writes (409). */
  readOnly: boolean
  rows: Partial<Record<CredentialId, CredentialRowVm>>
  /** A saved LLM key that cannot be decrypted overrides the environment value. */
  llmUnreadable: boolean
}

const CREDENTIAL_IDS: readonly CredentialId[] = [
  'OPENAI_API_KEY',
  'OPENAI_BASE_URL',
  'OPENAI_MODEL',
  'GITHUB_TOKEN',
  'HUGGINGFACE_TOKEN',
  'ZHIHU_ACCESS_SECRET',
  'BILIBILI_SESSDATA',
  'BILIBILI_BILI_JCT',
  'BILIBILI_BUVID3',
]

function toCredentialState(status: unknown): CredentialState {
  switch (status) {
    case 'ui':
      return 'app'
    case 'env':
      return 'env'
    case 'unreadable':
      return 'bad'
    default:
      return 'none'
  }
}

/** Read `GET /api/v1/settings/credentials` into the Keys panel view-model. */
export function toCredentialsVm(raw: unknown): CredentialsVm {
  if (!isRecord(raw) || !Array.isArray(raw.credentials)) {
    throw new Error('credential response is not a credential list')
  }
  const rows: Partial<Record<CredentialId, CredentialRowVm>> = {}
  for (const item of raw.credentials) {
    if (!isRecord(item) || typeof item.name !== 'string') {
      continue
    }
    const rowId = item.name === 'llm' ? 'OPENAI_API_KEY' : item.name
    if (!CREDENTIAL_IDS.includes(rowId as CredentialId)) {
      continue
    }
    const status = toCredentialState(item.status)
    rows[rowId as CredentialId] = {
      status,
      last4: status === 'app' || status === 'env' ? (item.last4 as string | null) : null,
      version: (item.version as string | null) ?? null,
    }
  }
  return {
    readOnly: raw.secret_key_configured !== true,
    rows,
    llmUnreadable: rows.OPENAI_API_KEY?.status === 'bad',
  }
}

/** The typed values in the Keys panel. A saved value never comes back here. */
export interface KeysDraft {
  llmKey: string
  llmUrl: string
  llmModel: string
  github: string
  hf: string
  zhihu: string
  bilibiliSessdata: string
  bilibiliBiliJct: string
  bilibiliBuvid3: string
}

export type KeyDraftKey = keyof KeysDraft

export const EMPTY_KEYS_DRAFT: KeysDraft = {
  llmKey: '',
  llmUrl: '',
  llmModel: '',
  github: '',
  hf: '',
  zhihu: '',
  bilibiliSessdata: '',
  bilibiliBiliJct: '',
  bilibiliBuvid3: '',
}

export interface CredentialTestOutcome {
  result: string
  reason: string
}

/** Everything the Keys panel renders. */
export interface KeysVm {
  readOnly: boolean
  llmUnreadable: boolean
  draft: KeysDraft
  rows: Partial<Record<CredentialId, CredentialRowVm>>
  /** Inline note per row (saved, refused, or cleared). */
  messages: Record<string, string>
  /** Newest test result per credential name. */
  results: Record<string, CredentialTestOutcome>
  /** Credential name whose test is in flight. */
  testing: string | null
  /** The newest GitHub check failed, so the Keys row offers the source warning. */
  githubAuthError: boolean
}
