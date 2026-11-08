import { beforeEach, describe, expect, it } from 'vitest'

import { authHeader, clearToken, getToken, installAuth, onUnauthorized, setToken } from '@/api/auth'
import { createClient } from '@/api/generated/client'

beforeEach(() => {
  sessionStorage.clear()
})

/** A generated client whose `fetch` records each outgoing request. */
function recordingClient(status = 200): {
  client: ReturnType<typeof createClient>
  seen: Request[]
} {
  const seen: Request[] = []
  const client = createClient({
    baseUrl: 'http://api.test',
    fetch: (async (request: Request) => {
      seen.push(request)
      return new Response('{"fake":false}', {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as typeof fetch,
  })
  installAuth(client)
  return { client, seen }
}

describe('owner token storage', () => {
  it('keeps the token in sessionStorage and turns it into a Bearer header', () => {
    expect(authHeader()).toEqual({})

    setToken('sekret')

    expect(getToken()).toBe('sekret')
    expect(authHeader()).toEqual({ Authorization: 'Bearer sekret' })

    clearToken()

    expect(getToken()).toBeNull()
    expect(authHeader()).toEqual({})
  })
})

describe('generated client auth', () => {
  it('sends Authorization only while a token is held', async () => {
    const { client, seen } = recordingClient()

    await client.get({ url: '/api/v1/health' })

    expect(seen[0].headers.get('Authorization')).toBeNull()

    setToken('sekret')
    await client.get({ url: '/api/v1/health' })

    expect(seen[1].headers.get('Authorization')).toBe('Bearer sekret')
  })

  it('notifies the unauthorized listener on a 401, and only on a 401', async () => {
    const calls: string[] = []
    const off = onUnauthorized(() => calls.push('401'))
    const unauthorized = recordingClient(401)
    const ok = recordingClient(200)

    await unauthorized.client.get({ url: '/api/v1/sessions' })
    await ok.client.get({ url: '/api/v1/sessions' })

    expect(calls).toEqual(['401'])

    off()
    await unauthorized.client.get({ url: '/api/v1/sessions' })
    expect(calls).toEqual(['401'])
  })
})
