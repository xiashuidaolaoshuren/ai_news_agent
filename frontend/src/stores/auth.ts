import { defineStore } from 'pinia'
import { reactive, toRefs } from 'vue'

import { clearToken, getToken, onUnauthorized, setToken } from '@/api/auth'
import { listSessionsApiV1SessionsGet } from '@/api/generated/sdk.gen'
import { setupApiClient } from '@/api/setupClient'

/** The prototype's copy for an empty field and for a token the API refused. */
export const BLANK_TOKEN_MESSAGE = 'Enter the owner access token.'
export const REJECTED_TOKEN_MESSAGE = 'That token was rejected.'
export const UNREACHABLE_MESSAGE = "Couldn't reach the server."

/** What the sign-in screen needs from the server, injected for tests. */
export interface AuthDeps {
  getToken(): string | null
  setToken(token: string): void
  clearToken(): void
  onUnauthorized(listener: () => void): () => void
  /** A request that needs the token. `/health` is exempt from auth, so it cannot be the probe. */
  probe(): Promise<{ status: number }>
}

/**
 * Sign-in state. Locked means the app is unreachable: the screen covers the shell
 * and the shell is inert until a token the API accepts is held.
 */
export function createAuthController(deps: AuthDeps, onUnlocked: () => void = () => {}) {
  const state = reactive({
    locked: false,
    error: null as string | null,
    busy: false,
  })

  /**
   * Any 401 locks the app. A token held at that moment was rejected, so drop it:
   * a reload cannot silently reuse it.
   */
  function lock(): void {
    if (state.locked) {
      return
    }
    const hadToken = deps.getToken() !== null
    deps.clearToken()
    state.busy = false
    state.locked = true
    state.error = hadToken ? REJECTED_TOKEN_MESSAGE : null
  }

  const off = deps.onUnauthorized(lock)

  /** Submit the typed token. A blank field never leaves the browser. */
  async function submit(raw: string): Promise<void> {
    const token = raw.trim()
    if (token === '') {
      state.error = BLANK_TOKEN_MESSAGE
      return
    }
    state.busy = true
    state.error = null
    deps.setToken(token)
    try {
      const { status } = await deps.probe()
      if (status === 401) {
        // The API refused this token: keep it out of the tab instead of retrying it.
        deps.clearToken()
        state.locked = true
        state.error = REJECTED_TOKEN_MESSAGE
        return
      }
      if (status < 200 || status >= 300) {
        // Anything but a clean answer proves nothing about the token.
        state.locked = true
        state.error = UNREACHABLE_MESSAGE
        return
      }
      state.locked = false
      state.error = null
      onUnlocked()
    } catch {
      // Unreachable is not a rejection: keep the token so a retry can use it.
      state.locked = true
      state.error = UNREACHABLE_MESSAGE
    } finally {
      state.busy = false
    }
  }

  return Object.assign(state, { lock, submit, dispose: off })
}

/** Production dependencies: the tab's token and a probe through the generated client. */
export function defaultAuthDeps(): AuthDeps {
  setupApiClient()
  return {
    getToken,
    setToken,
    clearToken,
    onUnauthorized,
    async probe(): Promise<{ status: number }> {
      const result = await listSessionsApiV1SessionsGet({ query: { limit: 1 } })
      return { status: result.response?.status ?? 0 }
    },
  }
}

/**
 * Bind the controller to a Pinia setup store. A setup store only keeps returned
 * refs live, so plain fields like `locked` and `error` must go through `toRefs`;
 * otherwise the screen would never follow a 401.
 */
export function toAuthStore(controller: ReturnType<typeof createAuthController>) {
  const { lock, submit, dispose } = controller
  return {
    ...toRefs(controller),
    lock,
    submit,
    dispose,
  }
}

export const useAuthStore = defineStore('auth', () =>
  toAuthStore(createAuthController(defaultAuthDeps())),
)
