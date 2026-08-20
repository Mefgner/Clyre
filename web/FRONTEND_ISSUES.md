# Clyre Frontend — Known Weaknesses

Triage of objectively weak parts of the Vue 3 frontend (`web/`), from an outside code review.
Line numbers are approximate — re-verify before fixing. Severity: high / medium / low.

## High

- **H1. Stream swallows fetch failures — cascading TypeError, no feedback**
  `web/repos/thread.ts:29-44` — `generateAssistantStream` catches network errors, logs them and implicitly returns `undefined`; the caller passes it to `readNDJSONStream`, which reads `response.body` → runtime `TypeError`. The user message was already pushed to the UI and is silently never sent.
- **H2. HTTP status of the streaming response never checked**
  `web/repos/thread.ts:32-40`, `web/utils/stream.ts:11-18`, `web/stores/thread.ts:116-145` — no `response.ok` anywhere in the stream path. A 401/500 JSON body is parsed as NDJSON (`event: undefined`), looks like an empty model answer. Token expiry is indistinguishable from an empty response.
- **H3. `isGenerating` set after `await fetch` — double-submit race**
  `web/stores/thread.ts:112-114`, `web/pages/index.vue:229-232` — two rapid Enter presses both pass the guard → two concurrent streams interleave into one message.
- **H4. 401-refresh interceptor refreshes on failed login attempts, can recurse**
  `web/utils/api.ts:30-54` — no exclusion for `/auth/login|register|refresh`. Wrong password enters the refresh path, can trigger recursive logout/refresh loops; `router.push('/')` is a navigation side-effect buried in the HTTP layer.
- **H5. No single-flight refresh — up to 3 concurrent `/auth/refresh` calls**
  `web/utils/api.ts:39-46`, `web/router/index.ts:37-44,65-73` — with a one-time refresh cookie, all but one fail → forced logout of a valid session.
- **H6. Login modal flickers during every background token refresh**
  `web/components/ModalContainer.vue:65`, `web/utils/api.ts:40` — interceptor nulls `accessToken` before refreshing, `watch(isLoggedIn)` opens the dialog momentarily.
- **H7. External CDN dependency in a privacy-first, local-first app**
  `web/components/chat/PrettyMarkdown.vue:19-21` — highlight.js themes load from `cdnjs.cloudflare.com` at runtime; leaks requests to a third party and breaks offline/local rendering.
- **H8. `v-html` with `marked`, no sanitization — XSS via LLM output**
  `web/components/chat/PrettyMarkdown.vue:43-50` — `marked` passes raw HTML through; injected via `v-html`. Prompt-injected content executes in the app origin holding the auth session. No DOMPurify anywhere.

## Medium

- **M1. Duplicate, racing event handling between store and page**
  `web/pages/index.vue:242-253` vs `web/stores/thread.ts:118-137` — both handle `user_message_insert` / `assistant_message_insert`; ~3 redundant requests per message, unawaited `.then()` chains, no cancellation, two racing `setCurrentThread` calls.
- **M2. `setCurrentThread` has no in-flight guard**
  `web/pages/chat.vue:9-14`, `web/stores/thread.ts:49-58` — watcher fires on every `threadsMeta` replacement (incl. 60s poll) and `chatId` change; out-of-order responses can show the wrong thread; unhandled rejection on fetch failure.
- **M3. Store pipeline swallows all non-abort errors — no error state in chat UI**
  `web/stores/thread.ts:146-149` — `catch { if not AbortError → console.error }`; a 500/dropped connection leaves a partial assistant message that looks complete. The protocol cannot express errors (`'error'` event commented out in `web/entities/thread.ts:3`).
- **M4. `deleteCurrentThread`: fire-and-forget, no error handling, no navigation**
  `web/stores/thread.ts:69-75`, `web/components/chat/AreYouSureModal.vue:13-16` — modal closes as if successful on failure; after a successful delete the route still points at the deleted `chatId` → blank chat forever.
- **M5. Login/register error mapping hides network errors**
  `web/components/ModalContainer.vue:34-63` — `if (!error?.status) return` → zero feedback on network failure; 422 `detail` array renders as `[object Object]`.
- **M6. `isMobile` snapshots a reactive value once**
  `web/pages/index.vue:166-168`, `web/components/chat/PromptBar.vue:47-48` — never updates on resize; should be a `computed`.
- **M7. 60s polling re-throws non-404 errors into an unawaited call, no visibility gating**
  `web/pages/index.vue:198-203`, `web/stores/thread.ts:29-43` — server down = unhandled rejection every 60s; inconsistent error policy.
- **M8. Mode selector is wired to nothing — dead UI**
  `web/components/chat/PromptBar.vue:24-34,59`, `web/pages/index.vue:228`, `web/stores/thread.ts:111` — the selected `mode` is forwarded as a `_` parameter and explicitly discarded.
- **M9. Stream reader never `cancel()`ed**
  `web/utils/stream.ts:49-51` — only `releaseLock()`, never `reader.cancel()`; the HTTP body stays open on early exit.
- **M10. Inconsistent transport config between axios and fetch**
  `web/utils/api.ts:9-15` vs `web/repos/thread.ts:32-40` — axios uses `baseURL` + `withCredentials`, the fetch path interpolates `VITE_API_URL` manually and sets no `credentials`; two hand-rolled auth injections that can drift.

## Low

- `@ts-ignore` / `any` holes: `api.ts:32,34`; `stream.ts:1,11` (`response: any`), `:42,47` (unparseable line becomes `{} as T` → `event: undefined` warning noise); `index.vue:244` (`currentThread!`); `ModalContainer.vue:57` (untyped `detail`).
- Dead code: `stores/thread.ts:104-109` (`generateAssistantMessage`, "don't use it"); `entities/thread.ts:32-34` (`ThreadHistoryCache` never referenced); `AreYouSureModal.vue:8` / `RegisterModal.vue:19` (`update:vModel` wrong-cased); `stream.ts:46` unreachable `\r\n`/`\r` clauses.
- Debug logging in production paths: `api.ts:7` (`console.log(VITE_API_URL)`), `repos/thread.ts:30`, `index.vue:49` (inline `console.log` in template).
- `validation.ts:13-15` — message says "3 to 30" but check allows 31.
- `chat.vue:9-14` — deep-link to unknown/deleted thread renders a silent blank chat; no loading state while history is in flight.
- `index.vue:43-44` — `Array.from(...).reverse()` per render; `:key` includes `String(index)` → defeats reconciliation.
- `App.vue:4` + `index.vue:127` double route-keying → full remounts, "New Chat" title flash on every thread switch.
- `stores/thread.ts:19-25` — `Date.now().toString()` (epoch ms) vs ISO strings from server in one field; `messages: reactive([])` in a factory into a `ref`.
- `stores/ui.ts` — state mutated directly from `ModalContainer.vue` instead of through actions.
- `PromptBar.vue:63` — whitespace-only prompt passes the guard; `:69-77` global keypress steals focus behind overlays.
- `chat.vue:16-19` — competing smooth `scrollIntoView` per streamed chunk jitters on long answers.

## Suggested fix order

1. H1 + H2 + M3 — end-to-end stream error handling (check `ok`, propagate, add an error event/state).
2. H3 — set `isGenerating` before the fetch / guard synchronously.
3. H4 + H5 + H6 — single-flight refresh with auth-endpoint exclusion; decouple the login modal from transient token state.
4. H7 + H8 — bundle highlight.js styles locally; sanitize markdown output.
5. M1 + M2 — consolidate event handling in the store; cancel/order thread fetches.
