# Owner token and provider credentials are separate boundaries

Status: accepted

The app is still single-owner, but a hosted backend can spend provider money and replace provider credentials. A shared owner token says who may do that. It does not make browser conversations into accounts. Shipping credential editing before that token, and treating a loopback client address as proof of locality, fails when a reverse proxy on the server presents remote callers as local.

Provider credentials have a second boundary. A saved override that cannot be decrypted is not the same as no override. Falling back to the environment would silently change which account is called. Saving the LLM key, endpoint, and model as separate fields would also let one request combine a new endpoint with an old key.

## Considered options (rejected)

- Ship credential editing first and add the owner token later — the write path would be reachable before its protection exists.
- Trust the client address in a remotely proxied deployment — the proxy can make a remote request look local.
- Store the owner token in `localStorage` by default — it survives browser restarts on a credential that can read every conversation and change provider keys.
- Treat an undecryptable override as unset — the environment credential would take over without an explicit owner action.
- Let the Settings screen point the LLM client at any URL — a signed-in page could direct the backend toward a private network. Public HTTPS is the remote default; private or plain-HTTP endpoints need a server-side allowance.
- Refuse to start until an LLM key exists — the owner could not open Settings to configure it.
- Call an owner token enough, by itself, for supported remote deployment — it does not bound authentication attempts, request size, or concurrent paid work.

## Decision

1. Remote mode refuses to start without `AI_NEWS_AGENT_ACCESS_TOKEN`. Credential editing ships only with that protection. Local mode may run without a token, and its credential writes are loopback-only. A reverse proxy uses remote mode.
2. The browser keeps the owner token in `sessionStorage`. Persistent "Remember me" is deferred.
3. A saved provider override that cannot be read is `unreadable` and blocks work that depends on it until the owner restores the key, replaces it, or deletes it.
4. The LLM key, base URL, and model are one configuration. Each request keeps the version it started with.
5. Remote-mode LLM endpoints are public HTTPS unless server configuration explicitly allows another destination. Redirects are held to the same rule.
6. Supported remote deployment also requires HTTPS, bounded request bodies, bounded concurrent paid operations, and throttling of failed authentication attempts. CORS remains a browser policy, not authentication.
7. The process starts when no LLM is configured. Only operations that need one ask for it. Fake mode stays explicitly selected.

## Consequences

- The owner access token is an HTTP requirement. The command line does not send it, but it does use the same provider-credential overrides and needs the encryption key to read them.
- Health observations are tied to a credential version. Replacing a credential makes older authentication results stale.
- Multi-user accounts and public visitor access remain out of scope.
