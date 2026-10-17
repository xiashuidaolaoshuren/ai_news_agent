import { API_BASE_URL } from '@/api/config'
import type {
  DeltaPayload,
  DigestPayload,
  DonePayload,
  ErrorPayload,
  PostMessageBody,
  ProgressPayload,
  StartedPayload,
} from '@/api/generated/types.gen'

/** One parsed SSE frame, discriminated by the backend event name. */
export type SseEvent =
  | { event: 'started'; data: StartedPayload }
  | { event: 'progress'; data: ProgressPayload }
  | { event: 'delta'; data: DeltaPayload }
  | { event: 'digest'; data: DigestPayload }
  | { event: 'done'; data: DonePayload }
  | { event: 'error'; data: ErrorPayload }

/** Blank line that ends one SSE frame, in LF or CRLF form. */
const FRAME_SEPARATOR = /\r?\n\r?\n/

const KNOWN_EVENTS = ['started', 'progress', 'delta', 'digest', 'done', 'error'] as const

type KnownEventName = (typeof KNOWN_EVENTS)[number]

function isKnownEvent(name: string): name is KnownEventName {
  return (KNOWN_EVENTS as readonly string[]).includes(name)
}

function parseFrame(frame: string): SseEvent | null {
  let name = ''
  let data = ''
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      name = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      data += line.slice('data:'.length).trim()
    }
  }
  if (!isKnownEvent(name) || data === '') {
    return null
  }
  try {
    return { event: name, data: JSON.parse(data) } as SseEvent
  } catch {
    return null
  }
}

/**
 * Parse `event: …\ndata: …\n\n` frames from a byte stream, yielding each frame
 * as soon as it completes rather than after the response ends. The reply, the
 * progress steps, and the run card all depend on that live delivery.
 */
export async function* parseSseStream(
  readable: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const reader = readable.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      buffer += decoder.decode(value, { stream: true })
      for (let match = FRAME_SEPARATOR.exec(buffer); match !== null; ) {
        const frame = buffer.slice(0, match.index)
        buffer = buffer.slice(match.index + match[0].length)
        const event = parseFrame(frame)
        if (event !== null) {
          yield event
        }
        match = FRAME_SEPARATOR.exec(buffer)
      }
    }
    buffer += decoder.decode()
  } finally {
    reader.releaseLock()
  }
  const trailing = parseFrame(buffer)
  if (trailing !== null) {
    yield trailing
  }
}

/** Non-2xx response from the streaming POST endpoint. */
export class SseHttpError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(status: number, code: string | null, message: string) {
    super(message)
    this.name = 'SseHttpError'
    this.status = status
    this.code = code
  }
}

export interface PostMessageStreamOptions {
  fetch?: typeof fetch
  signal?: AbortSignal
  baseUrl?: string
}

function extractDetailCode(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null) {
    return null
  }
  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail === 'string') {
    return detail
  }
  if (typeof detail === 'object' && detail !== null) {
    const code = (detail as { code?: unknown }).code
    if (typeof code === 'string') {
      return code
    }
  }
  return null
}

/**
 * POST a chat message and return the parsed SSE event stream.
 *
 * `EventSource` cannot POST, so the response body is read directly.
 */
export async function postMessageStream(
  sessionId: string,
  body: PostMessageBody,
  options: PostMessageStreamOptions = {},
): Promise<AsyncGenerator<SseEvent>> {
  const doFetch = options.fetch ?? fetch
  const baseUrl = options.baseUrl ?? API_BASE_URL
  const response = await doFetch(
    `${baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: options.signal,
    },
  )

  if (!response.ok) {
    let code: string | null = null
    try {
      code = extractDetailCode(await response.json())
    } catch {
      code = null
    }
    throw new SseHttpError(
      response.status,
      code,
      `POST messages failed with status ${response.status}`,
    )
  }

  const stream = response.body
  if (stream === null) {
    return (async function* empty() {})()
  }
  return parseSseStream(stream)
}
