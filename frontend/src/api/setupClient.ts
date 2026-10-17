import { client } from '@/api/generated/client.gen'
import { API_BASE_URL } from '@/api/config'

let configured = false

/** Point the generated OpenAPI client at the running backend (once). */
export function setupApiClient(): void {
  if (configured) {
    return
  }
  client.setConfig({ baseUrl: API_BASE_URL })
  configured = true
}
