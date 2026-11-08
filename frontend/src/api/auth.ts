import type { Client } from '@/api/generated/client'

/** `sessionStorage` key for the owner access token. One tab, cleared on close. */
export const TOKEN_KEY = 'ai_news_owner_token'

/** The token held for this tab, or null when the user has not signed in. */
export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/** Remember the owner token for this tab only; never send it anywhere but the API. */
export function setToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage blocked (private mode or a sandboxed frame): the tab stays unlocked
    // for this page view, which is the same lifetime as the session store.
  }
}

/** Drop the token, so the next request is unauthenticated and locks the app. */
export function clearToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing held; nothing to clear.
  }
}

/** Authorization header for a raw `fetch`, or nothing when no token is held. */
export function authHeader(): Record<string, string> {
  const token = getToken()
  return token === null || token === '' ? {} : { Authorization: `Bearer ${token}` }
}

type UnauthorizedListener = () => void

const unauthorizedListeners = new Set<UnauthorizedListener>()

/**
 * Called whenever the API answers 401. Returns the unsubscribe function, so the
 * auth store can drop its listener when the app unmounts.
 */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener)
  return () => {
    unauthorizedListeners.delete(listener)
  }
}

/** Every 401 funnels here, from generated-client calls and from the raw SSE POSTs. */
export function notifyUnauthorized(): void {
  for (const listener of [...unauthorizedListeners]) {
    listener()
  }
}

/**
 * Attach the tab's owner token to every generated-client request. Installed once
 * from `setupApiClient`, so Settings, the session list, and the message POST all
 * carry the same header as the raw SSE streams.
 */
export function installAuth(client: Client): void {
  client.interceptors.request.use((request) => {
    const token = getToken()
    if (token !== null && token !== '') {
      request.headers.set('Authorization', `Bearer ${token}`)
    }
    return request
  })
  client.interceptors.response.use((response) => {
    if (response.status === 401) {
      notifyUnauthorized()
    }
    return response
  })
}
