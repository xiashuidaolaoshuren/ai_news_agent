import { createPinia, defineStore, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { clearToken, getToken, setToken } from '@/api/auth'
import { createAuthController, toAuthStore, type AuthDeps } from '@/stores/auth'

beforeEach(() => {
  sessionStorage.clear()
})

/** Injected auth deps: real token storage, a listener registry, a scripted probe. */
function fakeDeps(options: { status?: number; throws?: boolean } = {}): {
  deps: AuthDeps
  listeners: Set<() => void>
  probeCalls: () => number
} {
  const listeners = new Set<() => void>()
  let probes = 0
  return {
    listeners,
    probeCalls: () => probes,
    deps: {
      getToken,
      setToken,
      clearToken,
      onUnauthorized: (listener) => {
        listeners.add(listener)
        return () => {
          listeners.delete(listener)
        }
      },
      probe: async () => {
        probes += 1
        if (options.throws === true) {
          throw new Error('offline')
        }
        return { status: options.status ?? 200 }
      },
    },
  }
}

describe('auth controller', () => {
  it('locks when a 401 is reported, and forgets the rejected token', () => {
    const { deps, listeners } = fakeDeps()
    const auth = createAuthController(deps)
    setToken('stale')

    for (const listener of listeners) {
      listener()
    }

    expect(auth.locked).toBe(true)
    expect(auth.error).toBe('That token was rejected.')
    expect(getToken()).toBeNull()
  })

  it('asks for a token instead of sending a blank one', async () => {
    const { deps, probeCalls } = fakeDeps()
    const auth = createAuthController(deps)

    await auth.submit('   ')

    expect(auth.error).toBe('Enter the owner access token.')
    expect(probeCalls()).toBe(0)
  })

  it('keeps the screen up for a rejected token and forgets it', async () => {
    const { deps } = fakeDeps({ status: 401 })
    const auth = createAuthController(deps)

    await auth.submit('bad')

    expect(auth.locked).toBe(true)
    expect(auth.error).toBe('That token was rejected.')
    expect(auth.busy).toBe(false)
    expect(getToken()).toBeNull()
  })

  it('unlocks with an accepted token, keeps it, and reloads the app', async () => {
    const { deps } = fakeDeps({ status: 200 })
    let reloads = 0
    const auth = createAuthController(deps, () => {
      reloads += 1
    })
    auth.lock()

    await auth.submit('good')

    expect(auth.locked).toBe(false)
    expect(auth.error).toBeNull()
    expect(getToken()).toBe('good')
    expect(reloads).toBe(1)
  })

  it('keeps the token when the server cannot be reached', async () => {
    const { deps } = fakeDeps({ throws: true })
    const auth = createAuthController(deps)

    await auth.submit('good')

    expect(auth.locked).toBe(true)
    expect(auth.error).toBe("Couldn't reach the server.")
    expect(getToken()).toBe('good')
    expect(auth.busy).toBe(false)
  })

  it('does not unlock on a server error', async () => {
    const { deps } = fakeDeps({ status: 503 })
    const auth = createAuthController(deps)

    await auth.submit('good')

    expect(auth.locked).toBe(true)
    expect(auth.error).toBe("Couldn't reach the server.")
    expect(getToken()).toBe('good')
  })
})

describe('auth Pinia store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('exposes the lock state through the store, not only the controller', () => {
    const { deps } = fakeDeps()
    const useTestAuth = defineStore('test-auth', () =>
      toAuthStore(createAuthController(deps)),
    )
    const store = useTestAuth()

    store.lock()

    expect(store.locked).toBe(true)
  })
})
