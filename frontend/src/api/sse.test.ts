import { describe, expect, it } from 'vitest'

import { SseHttpError, parseSseStream, postMessageStream, type SseEvent } from '@/api/sse'

/** Build a one-shot byte stream from raw byte chunks (no implicit framing). */
function byteStream(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(chunk)
      }
      controller.close()
    },
  })
}

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return byteStream(chunks.map((chunk) => encoder.encode(chunk)))
}

async function collect(readable: AsyncIterable<SseEvent>): Promise<SseEvent[]> {
  const events: SseEvent[] = []
  for await (const event of readable) {
    events.push(event)
  }
  return events
}

describe('parseSseStream', () => {
  it('parses one frame into a typed event', async () => {
    const frame = 'event: started\ndata: {"request_id":"r1","user_message_id":7}\n\n'

    await expect(collect(parseSseStream(streamOf([frame])))).resolves.toEqual([
      { event: 'started', data: { request_id: 'r1', user_message_id: 7 } },
    ])
  })

  it('reassembles a frame split across chunks, including a split multibyte character', async () => {
    const bytes = new TextEncoder().encode('event: delta\ndata: {"text":"héllo ✓"}\n\n')
    const lead = bytes.indexOf(0xc3)
    const chunks = [
      bytes.slice(0, lead + 1),
      bytes.slice(lead + 1, bytes.length - 3),
      bytes.slice(bytes.length - 3),
    ]

    await expect(collect(parseSseStream(byteStream(chunks)))).resolves.toEqual([
      { event: 'delta', data: { text: 'héllo ✓' } },
    ])
  })

  it('parses several frames from one chunk and accepts CRLF endings', async () => {
    const chunk =
      'event: progress\r\ndata: {"stage":"Calling github…"}\r\n\r\n' +
      'event: delta\r\ndata: {"text":"one"}\r\n\r\n' +
      'event: done\r\ndata: ' +
      '{"request_id":"r1","message_id":3,"run_id":null,"path":"followup"}\r\n\r\n'

    await expect(collect(parseSseStream(streamOf([chunk])))).resolves.toEqual([
      { event: 'progress', data: { stage: 'Calling github…' } },
      { event: 'delta', data: { text: 'one' } },
      {
        event: 'done',
        data: { request_id: 'r1', message_id: 3, run_id: null, path: 'followup' },
      },
    ])
  })

  it('ignores comments, unknown events, and malformed payloads', async () => {
    const chunk =
      ': keep-alive\r\n\r\n' +
      'event: heartbeat\r\ndata: {"at":1}\r\n\r\n' +
      'event: delta\r\ndata: {"text":"ok"}\r\n\r\n' +
      'event: delta\r\ndata: {not json}\r\n\r\n' +
      'event: delta\r\ndata: {"text":"last"}\r\n\r\n'

    await expect(collect(parseSseStream(streamOf([chunk])))).resolves.toEqual([
      { event: 'delta', data: { text: 'ok' } },
      { event: 'delta', data: { text: 'last' } },
    ])
  })
})

describe('postMessageStream', () => {
  it('POSTs the body as an SSE stream', async () => {
    const calls: Array<{ url: string; init: RequestInit }> = []
    const fakeFetch = (async (url: string | URL, init: RequestInit) => {
      calls.push({ url: String(url), init })
      return new Response(
        'event: started\ndata: {"request_id":"r1","user_message_id":1}\n\n',
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
      )
    }) as unknown as typeof fetch

    const stream = await postMessageStream(
      's1',
      { content: 'hi', client_request_id: 'c1', juya_item_mode: 'stories' },
      { fetch: fakeFetch, baseUrl: 'http://api.test' },
    )

    await expect(collect(stream)).resolves.toEqual([
      { event: 'started', data: { request_id: 'r1', user_message_id: 1 } },
    ])
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('http://api.test/api/v1/sessions/s1/messages')
    expect(calls[0]?.init.method).toBe('POST')
    expect(calls[0]?.init.headers).toMatchObject({
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    })
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({
      content: 'hi',
      client_request_id: 'c1',
      juya_item_mode: 'stories',
    })
  })

  it('throws SseHttpError carrying the 409 detail code', async () => {
    const fakeFetch = (async () =>
      new Response(JSON.stringify({ detail: { code: 'session_busy' } }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      })) as unknown as typeof fetch

    await expect(
      postMessageStream(
        's1',
        { content: 'hi' },
        { fetch: fakeFetch, baseUrl: 'http://api.test' },
      ),
    ).rejects.toMatchObject({ name: 'SseHttpError', status: 409, code: 'session_busy' })

    expect(new SseHttpError(500, null, 'boom')).toBeInstanceOf(Error)
  })
})
