# Implementation plan: Follow-ups and settings, frontend

**Piece:** 2 of 2. Backend: `docs/superpowers/plans/2026-10-20-followups-settings-backend-plan.md`
**Specs:** `docs/superpowers/specs/2026-10-20-targeted-followups-design.md`, `docs/superpowers/specs/2026-10-20-settings-and-credentials-design.md`
**ADRs:** `docs/adr/0010-web-story-mode-and-session-source-preferences.md` (decision 2 superseded: the per-source stepper goes away), `docs/adr/0013-global-source-profiles.md`, `docs/adr/0014-owner-access-and-credential-boundary.md`
**Prototype:** OpenDesign project "AI News Research Agent", file `research-chat-prototype.html`. Not `research-chat-prototype-v1.html`.
**Created:** 2026-10-30
**Goal scope:** One frontend piece: the prototype's follow-up controls, loading and collection states, Settings (Sources and Keys), and the sign-in screen. It binds to the backend piece. OpenRouter as a selectable digest source, and research controls, stay out.

## Summary

The thread replaces "Ask a follow-up" with Deep dive and Ask about this, the reference chip, `re: #n`, Related, the loading skeleton, and the three collection states. The composer loses its count stepper. A Settings button opens Sources and Keys. Gears on visible source chips open that source's section. Sign-in appears when the API returns 401, stores the token in `sessionStorage`, and sends it on API and SSE requests.

Visual source is the current prototype: anchors, chip text, settings dialog, keys rows, and the sign-in form. Do not redesign them.

## Discovery notes

- Reuse: `EntryRow.vue` `.entry-foot` and one "Ask a follow-up" button that calls `prefillFollowUp(title)`. `HfTable.vue` has no Actions column. `Thread.vue` shows `EmptyConversation` whenever `messages.length === 0`, including during load. `thread.loading` and `thread.loadError` already exist.
- Reuse: `Composer.vue` count stepper (`stepCount`) writes `items_per_source` on the session. This piece removes that control. Source checkboxes stay session preferences.
- Reuse: sidebar footer in `Sidebar.vue` for the Settings button (`settings-button` in the prototype). Generated client already has an auth helper in `frontend/src/api/generated/core/auth.gen.ts`.
- Prototype follow-up anchors: `deepdive-{id}`, `followup-{id}`, `composer-ref-chip`, `message-ref-chip`, `reply-ref-link`, `related-{rank}`, `digest-run-again`, `conversation-loading`, `conversation-load-failed`, `retry-load`, `no-eligible-results`, `try-{source}`, `collection-failed`, `retry-collection`. Chip text is `↳ d{id} #{rank}` plus the title. Reply link text is `re: #{rank}`. Related text is `Related: #{rank}`.
- Prototype settings anchors: `settings-dialog`, `settings-source-{k}`, `settings-output-language`, `source-settings-{k}`, `source-count-notice`, `juya-all-confirm`, `juya-confirm-cancel`, `juya-confirm-continue`, `keys-read-only`, `keys-unreadable-override`, `key-row-{id}`, `save-llm`, `github-auth-warning`, `sign-in-screen`, `sign-in-button`. Rejected-token copy is `That token was rejected.`
- Constraint: Keys and sign-in wait until backend **B9**, **B10**, and **B11** are done. Do not build the Keys tab against an API that still accepts non-loopback writes without a token.
- Constraint: the OpenRouter digest section, free-pricing badge, and composer checkbox are the OpenRouter spec. This piece still renders the OpenRouter block inside Settings, because the settings spec stores that profile.
- Constraint: research is not a third entry button. That arrives in the research plan's **R9**, using the entry foot this piece creates.
- Anti-goals: no second visual language, no Remember-me control, no multi-user accounts, no OpenRouter collect UI.

## File map

### Goal: Follow-up thread

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `frontend/src/vm/types.ts` | modify | Target, collection outcome, related ranks | `EntryVm`, message vm | verified |
| `frontend/src/vm/digest.ts` | modify | Map new entry fields | `toDigestVm` | verified |
| `frontend/src/vm/session.ts` | modify | User chip and reply ref | message mapper | verified |
| `frontend/src/components/thread/EntryRow.vue` | modify | Deep dive, Ask about this, Related | `deepdive-*`, `followup-*`, `related-*` | verified |
| `frontend/src/components/thread/HfTable.vue` | modify | Actions column | `hf-row-{rank}` | verified |
| `frontend/src/components/thread/DigestReply.vue` | modify | Run again foot | `digest-run-again` | verified |
| `frontend/src/components/thread/ConversationSkeleton.vue` | create | First-load skeleton | `conversation-loading` | verified |
| `frontend/src/components/thread/LoadFailed.vue` | create | Transcript load error and retry | `conversation-load-failed`, `retry-load` | verified |
| `frontend/src/components/thread/NoEligibleResults.vue` | create | Finished empty collect and try-source buttons | `no-eligible-results`, `try-{source}` | verified |
| `frontend/src/components/thread/CollectionFailed.vue` | create | Source collect failure and retry | `collection-failed`, `retry-collection` | verified |
| `frontend/src/components/thread/Thread.vue` | modify | Chips, reply link, skeleton, collection states | thread anchors | verified |
| `frontend/src/App.vue` | modify | Wire opening, load error, catalog, and repeat | — | verified |
| `frontend/src/components/composer/Composer.vue` | modify | Reference chip; stepper removed in U3 | `composer-ref-chip` | verified |
| `frontend/src/stores/composer.ts` | modify | Hold a target instead of a pasted sentence | composer store | verified |
| `frontend/src/stores/thread.ts` | modify | Send target, action, and repeat fields | thread store | verified |
| `frontend/src/styles/thread.css` | modify | `.ref-chip`, `.rel-chip`, `.re`, `.skel`, `.row-acts` | CSS | verified |
| `frontend/src/styles/composer.css` | modify | Composer chip | CSS | verified |

### Goal: Settings, keys, and sign-in

| Path | Create/Modify | Responsibility | Public surface | Verified/Provisional |
|---|---|---|---|---|
| `frontend/src/components/sidebar/Sidebar.vue` | modify | Settings button in the footer | `settings-button` | verified |
| `frontend/src/components/settings/SettingsDialog.vue` | create | Sources and Keys tabs | `settings-dialog` | provisional |
| `frontend/src/components/settings/SourceSettings.vue` | create | One section per profile, including hidden Bilibili and OpenRouter | `settings-source-{k}` | provisional |
| `frontend/src/components/settings/KeysPanel.vue` | create | Write-only credentials and tests | `key-row-*`, `save-llm` | provisional |
| `frontend/src/components/settings/SignIn.vue` | create | Locked sign-in screen | `sign-in-screen` | provisional |
| `frontend/src/stores/settings.ts` | create | Load and save profiles, language, credentials | settings store | provisional |
| `frontend/src/stores/auth.ts` | create | `sessionStorage` token and 401 handling | auth store | provisional |
| `frontend/src/api/client.ts` | modify | Attach `Authorization` on HTTP and SSE | existing client setup | verified path; filename provisional if the attach point lives in `api/config.ts` |
| `frontend/src/components/composer/Composer.vue` | modify | Remove the stepper; add source gears; one-time notice | `source-settings-*`, `source-count-notice` | verified |
| `frontend/src/components/thread/Thread.vue` | modify | Juya confirmation panel | `juya-all-confirm` | verified |
| `frontend/src/styles/thread.css` | modify | Dialog, keys, and sign-in rules copied from the prototype | CSS | verified |

### Blast radius

| Path | Why sensitive | Behavior that must stay intact | Plan mode |
|---|---|---|---|
| `Thread.vue` | Every conversation | Digest, cancel, interrupt, and reconnect rendering | high |
| `Composer.vue` | Every send | Source checkboxes still persist as session preferences | high |
| `api` client | Every request, including SSE | Requests without a token still work in local mode | high |
| `Sidebar.vue` | Session list | New, search, rename, delete, theme | medium |

## Workflow (for implementers)

1. **writing-plans** produced this file (type-1 decomposition only).
2. Regenerate `frontend/src/api/generated/` from the backend OpenAPI before a UI task that sends the new fields. **U1** waits for backend **B1** and **B2**. **U2** waits for **B4**. **U3** waits for **B6**, **B7**, and **B8**. **U4** and **U5** wait for **B9**, **B10**, and **B11**.
3. Per subtask: **Plan mode** + **planning-subtasks** when **Plan mode** is `high` or `medium` with a named unknown.
4. **`partial`** means test the payload and state, and check layout against the OpenDesign preview.

## Subtasks

### U1 — Entry actions and reference chips

- [ ] **Do:** Replace the pasted follow-up sentence with the prototype's Deep dive, Ask about this, chip, reply link, and Related chip.
- **Consumes:** Backend **B1** and **B2**. Prototype `entryActs`, `refChip`, `reply-ref-link`, `rel-chip`, and the Hugging Face actions cell.
- **Produces:** Deep dive sends `followup_target` and `deep_dive` immediately. Ask about this shows the removable composer chip and sends `ask`. Table buttons use `aria-label="Deep dive: {title}"` and `aria-label="Ask about this: {title}"`. Chip text is `↳ d{id} #{rank}` plus the title. Remove control label is `Remove reference to d{id} #{rank}`. Placeholder is `Ask about d{id} #{rank}…` while the chip is present. User bubbles restore `message-ref-chip`. Assistant labels show `re: #{rank}` and scroll to `data-ref="d{id}-{rank}"`. Related shows only when `related_display_ranks` is non-empty.
- **Acceptance:** Deep dive and Ask about this work from a block row and from a comparison-table row. Removing the chip sends a plain message. Reload restores the chip and the reply link. `re: #n` and Related scroll to that entry. Replies stay Markdown. A 400 for a missing entry shows "That entry is no longer available" and clears the chip. There is no research button.
- **Compatibility:** Hover previews, avatars, and digest layout stay.
- **Blocked by:** B1, B2
- **Plan mode:** high
- **TDD suitable:** partial
- **TDD suitable reason:** the send payload, chip removal, and scroll target are testable; spacing is checked against the prototype.
- **Verification:** `npm test -- --run src/components/thread/entry-row.test.ts src/components/thread/hf-table.test.ts src/components/thread/digest.test.ts src/components/composer/Composer.test.ts src/stores/composer.test.ts` from `frontend/`, then a browser pass of Deep dive, Ask about this, chip removal, reload, and `re: #n`.

### U2 — Loading and collection states

- [ ] **Do:** Show the prototype skeleton, load error, no-results suggestions, collection failure, and digest-foot Run again.
- **Consumes:** Backend **B4**. `thread.opening` (first open and retry only; `thread.loading` also covers post-run reloads), `thread.loadError`. Prototype `renderSkeleton`, `renderNoResults`, `collection-failed`, and `digest-run-again`.
- **Produces:** `conversation-loading` during the first messages request. `empty-conversation` only after a successful load with no messages. `conversation-load-failed` with `retry-load`. `no-eligible-results` with up to three `try-{source}` buttons. `collection-failed` with `retry-collection`. Partial digests keep their entries and name the failed source. `digest-run-again` sends `repeat_of_user_message_id` and shows the prototype help sentence.
- **Acceptance:** A conversation that already has digests does not flash "Start a digest". The empty state appears only when loading has finished and there are no messages. A failed load shows Retry and does not wipe saved messages. No-results buttons state the topic and timeframe and send `replace_source`. Failure is not titled as no eligible results. Run again does not only refill the composer.
- **Compatibility:** Cancelled, interrupted, and reconnect banners stay.
- **Blocked by:** B4
- **Plan mode:** medium (named unknown: whether `thread.loading` is already true before `Thread` renders the new session)
- **TDD suitable:** partial
- **TDD suitable reason:** outcome selection and the repeat payload are testable; the skeleton is checked against the prototype.
- **Verification:** `npm test -- --run src/vm/session.test.ts src/stores/thread.test.ts src/stores/composer.test.ts src/components/thread/thread.test.ts src/components/thread/digest.test.ts` from `frontend/`, then a browser pass of loading, empty, load error, no-results, failure, partial, and Run again.

### U3 — Sources settings

- [ ] **Do:** Open the prototype Settings dialog on Sources, remove the composer stepper, and confirm large Juya requests.
- **Consumes:** Backend **B6**, **B7**, and **B8**. Prototype settings dialog, source gears, `source-count-notice`, and `juya-all-confirm`.
- **Produces:** `settings-button` opens `settings-dialog` on the Sources tab. Each source section matches `settings-source-{k}`, including Bilibili labelled "Hidden from source selection" and the OpenRouter profile fields. Output language is `settings-output-language`. A gear (`source-settings-{k}`) opens that section. The composer stepper is gone and sends no shared count. Source checkboxes remain. The one-time `source-count-notice` says new requests use the global source counts from Settings, initially 5 per source. `juya-all-confirm` offers Cancel and Continue. Invalid profile fields show the API's field message inline. Saved settings apply to the next request.
- **Acceptance:** The panel lists profiles from `GET /settings/sources` and saves with PUT, including a hidden source. The gear opens the matching section. The composer has no count stepper. The notice shows once per browser. More than 20 Juya stories shows the confirm panel and does not start the digest until Continue. Cancel leaves no digest. Entry text already generated in `en` or `zh-CN` is shown as returned; this task does not translate the English chrome the prototype keeps.
- **Compatibility:** Session source checkboxes still PATCH the session. Bilibili disappears from the composer and remains in Settings.
- **Blocked by:** B6, B7, B8
- **Plan mode:** high
- **TDD suitable:** partial
- **TDD suitable reason:** save payloads, gear target, stepper removal, and confirm actions are testable; dialog layout is checked against the prototype.
- **Verification:** `npm test -- --run src/components/composer/Composer.test.ts src/stores/composer.test.ts src/components/settings` from `frontend/`, then a browser pass of Settings, a gear, the notice, and Juya confirm.

### U4 — Keys

- [ ] **Do:** Add the Keys tab from the prototype: status only, write-only inputs, read-only mode, and the unreadable state.
- **Consumes:** Backend **B9**, **B10**, and **B11**. Prototype `key-row-*`, `save-llm`, `keys-read-only`, `keys-unreadable-override`, and `github-auth-warning`.
- **Produces:** Keys shows `status` and `last4`, never a stored value. LLM key, base URL, and model save together on `save-llm`. The test control says the LLM check may incur a small charge. A 409 write shows the read-only explanation. `unreadable` is distinct from unset and can be cleared. A health dot and tooltip on the composer chip follow the current credential version. "Not checked since update" shows after a change until a new observation exists. The GitHub auth link jumps to the GitHub key row.
- **Acceptance:** The form never displays a secret returned by the API, because the API has none. Saving the LLM sends one PUT. A source test result is the sanitized reason. Read-only mode disables writes and explains the missing secret key. The health dot matches `GET /api/v1/sources` for the current version. Bilibili keys remain editable.
- **Compatibility:** Sources tab from U3 stays. Local mode without a token still loads Keys from loopback.
- **Blocked by:** B9, B10, B11
- **Plan mode:** high
- **TDD suitable:** partial
- **TDD suitable reason:** the write and test payloads are testable; masking and the read-only panel are checked against the prototype.
- **Verification:** `npm test -- --run src/components/settings src/stores/settings.test.ts` from `frontend/`, then a browser pass of save, test, read-only, and unreadable.

### U5 — Sign-in

- [ ] **Do:** Lock the app on 401 and attach the owner token from `sessionStorage`.
- **Consumes:** Backend **B11**. Prototype `sign-in-screen` and `sign-in-button`. Generated auth helper.
- **Produces:** A missing or rejected token shows the sign-in screen and leaves the rest of the app unreachable. The token is stored in `sessionStorage` and sent as `Authorization: Bearer` on API requests and SSE. Closing the tab clears it. A rejected token stays masked and shows `That token was rejected.` There is no Remember-me control.
- **Acceptance:** A 401 from any `/api/v1` route except a successful `/health` opens sign-in. After a successful token, Settings and chat load. A wrong token keeps the screen up and does not flash the conversation. SSE sends the same header. Reloading the tab keeps the token; closing it does not. Local mode without a 401 never shows sign-in.
- **Compatibility:** Fake mode and local loopback without a token still open the app.
- **Blocked by:** B11
- **Plan mode:** high
- **TDD suitable:** partial
- **TDD suitable reason:** token storage and the Authorization header are testable; the locked screen is checked against the prototype.
- **Verification:** `npm test -- --run src/stores/auth.test.ts src/api` from `frontend/`, then a browser pass of sign-in, a rejected token, and a chat SSE request that carries the header.

### U6 — Frontend contract check

- [ ] **Do:** Regenerate the client and run the frontend suite against the finished backend contracts.
- **Consumes:** U1–U5 and backend **B12**.
- **Produces:** An updated `frontend/src/api/generated/` that includes follow-up fields, settings routes, and credential routes.
- **Acceptance:** The generated client compiles. `npm test -- --run` passes. A manual pass covers fake mode, a live settings save, and a remote-mode 401.
- **Blocked by:** U1, U2, U3, U4, U5, B12
- **Plan mode:** skip
- **TDD suitable:** partial
- **TDD suitable reason:** the suite is the check; the manual pass is the remote-mode and fake-mode confirmation.
- **Verification:** `npm test -- --run` from `frontend/`.

## TDD note (Agent mode)

Per subtask, obey **`TDD suitable`**. **`partial`** tests behavior and checks the OpenDesign preview for layout. Do not add prototype screens that belong to the OpenRouter digest or to research.

## Plan changelog

| Date | Change | Kind |
|---|---|---|
| 2026-10-30 | Split from `2026-10-20-targeted-followups-plan.md`. Follow-up UI is U1–U2. Settings, Keys, and sign-in from the settings spec and the current prototype are U3–U5. | material |
| 2026-11-06 | U2 file map names the four collection-state components, `App.vue`, and `thread.opening`. Verification adds the session, composer, and digest tests. | equivalent |
