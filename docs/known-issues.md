# Known Weaknesses (External Review)

Findings from a multi-agent code review of areas **not** slated for rework in `PLAN.md`.
When editing any file listed here, read this document first and address or explicitly
avoid regressing the noted problem. Fix opportunistically; do not expand scope.

Status markers: `[ ]` open, `[x]` fixed.

## Critical

### 1. XSS via unsanitized markdown rendering — `web/components/chat/PrettyMarkdown.vue:50`
`v-html="rendered"` renders LLM output through `marked` with no DOMPurify. Any HTML/JS
injected into model output executes in the app origin (which holds the Bearer token).
Fix: `DOMPurify.sanitize(markedParser.parse(...))`.

### 2. Path traversal in SPA fallback — `api/app.py:44-49`
`candidate = _DIST_DIR / full_path` has no containment check before `FileResponse`.
A request like `GET /..%2f..%2f.env` escapes `web/dist`. Real exposure on the Docker /
team-server shape. Fix: `candidate.resolve()` + verify it is under `_DIST_DIR.resolve()`.

### 3. Chat "streaming" is not streaming — `web/repos/thread.ts:25-30`, `stores/thread.ts`
Axios (`responseType: 'text'`) buffers the entire NDJSON body before first paint; the
stop button does nothing; there is no `AbortController` anywhere. Additionally,
switching threads mid-generation splices old messages onto the new thread and streams
tokens into the wrong view (`stores/thread.ts:52-57`). Fix: `fetch` +
`response.body.getReader()` with an incremental line buffer, per-request abort, and
binding stream output to a thread id.

### 4. llama-server subprocess handling — `scripts/llama_launcher.py:69`, `run-desktop.py`
- stdout/stderr are piped but never drained → OS pipe buffer fills (~64 KB) and
  llama-server freezes; surfaces as a misleading `ConnectionError` after 300 s.
- Returned `Popen` handles are discarded; no terminate/kill/atexit anywhere → orphaned
  processes hold ports 6760–6762 and VRAM after Ctrl+C or crash.
Fix: redirect to log files / DEVNULL and wrap startup-to-shutdown in try/finally that
terminates and waits on every child (process group / job object on Windows).

## Medium

### 5. Zero test coverage above the service layer — `tests/`, `tests_e2e/`
No tests for `ChattingService`, `/api/chat/*` (NDJSON wire contract), auth routes,
thread routes, files routes, user `/me`. The save-on-disconnect path
(`api/services/chatting.py:150-224`) is the most intricate code in the backend and is
uncovered. Cheapest to add before Phase 5.
Partial progress: the generation core (`/api/chat/stream|stop|retry`, pub/sub,
start race, finalize failure, crash sweep) now has unit + live e2e coverage
(`tests/test_chat_stream.py`, `tests/test_generation_unit.py`, `tests_e2e/*`);
auth/thread/file/user routes remain open.

### 6. Docker compose hygiene — `docker-compose.yml`
- Hardcoded `POSTGRES_PASSWORD: clyre_secret` (lines 31-33) while app secrets correctly
  use `${VAR:?}` — make DB credentials env-required too.
- Ports 6760/6761 published to LAN; llama-server has no auth. Drop mappings or bind to
  127.0.0.1.
- No healthcheck or `restart:` policy on the api service.

### 7. Authorization header logged + raw exception to client — `api/app.py:76`
The global handler logs the full `Request` object (includes the Bearer token) and
returns `str(exc)` to clients. Log url + method only; return a generic 500 body.

### 8. Per-request httpx clients + unbounded gather — `api/pipelines/inference.py`,
`api/pipelines/embed.py`
Every call builds a fresh `AsyncClient` (no keep-alive on the hottest path);
`count_tokens_many` fires N concurrent POSTs with no semaphore. Hold one client per
pipeline instance with explicit `aclose()`, cap concurrency with `asyncio.Semaphore`.

Also in this area:
- SSE parsing assumes exactly `"data: "` prefix (`inference.py:145`) — comment/keepalive
  lines produce ERROR-level log noise.
- Whole `texts` list in one embed POST can exceed embedding ctx/timeout — batch
  client-side (`embed.py:53`).

### 9. Token-refresh stampede + fail-open logout — `web/utils/api.ts:28-55`,
`web/stores/auth.ts:36`
N parallel 401s each trigger their own refresh while rotation invalidates cookies →
spurious logout. Share one in-flight refresh promise. Logout should clear local state
regardless of backend success and have a `.catch`.

### 10. [x] Datetime inconsistency — repo-wide
Naive vs aware UTC patched ad hoc at each site (`utils/web.py:68-69,104`,
`services/auth.py:114-115`, `services/file.py:64`); `get_current_timestamp()` returns
naive local time. Consolidate on one aware-UTC helper. Also `utc_from_iso_str`
(`api/utils/timing.py:16`) is dead and broken (discards the parsed value, returns now).

### 19. Auth error-mapping edge cases — `routes/auth/views.py`,
`routes/user/views.py`, `utils/web.py`, `utils/hashing.py`
- Login runs the full registration password policy (`views.py:84`): accounts
  predating the policy get 422 before credentials are checked. Validate email
  only on login.
- Concurrent registers race the existence check → IntegrityError → 500
  (`views.py:107`); map to 400 "email exists".
- `routes/user/views.py:34` `except Exception` → 404 "User does not exist"
  masks DB outages; catch the service ValueError only.
- `utils/web.py:40` `token_dict["timestamp"]` KeyError → 500 on a signed
  token without the claim; missing refresh cookie yields 422 instead of 401.
- `utils/hashing.py:25` catches only VerifyMismatchError: a corrupted stored
  hash raises InvalidHashError → 500 on login. Catch VerificationError.
- Dead `session.commit()` after `register_locally` (`views.py:113`) — the
  service already commits (same ownership confusion as #12).

### 20. Inference client operational assumptions — `pipelines/inference.py`
- Streaming call uses a flat 60 s timeout (:188), but llama-server is silent
  during prompt processing; a multi-k-token prompt can exceed it before the
  first token and ReadTimeout kills a healthy generation. Use connect ~10 s /
  read ~300 s.
- `chat_completion_sync` unconditionally reads llama-only `timings`/`id` keys
  (:161) → KeyError → 500 on any other OpenAI-compatible server after a
  successful generation; `.get()` them.

### 21. File lifecycle gaps — `services/file.py`, `services/ingestion.py`
- `delete_user_file` deletes the blob before the commit (:184): a failed
  commit strands metadata without bytes → later fetches 500 (upload has a
  compensating delete; delete doesn't).
- Crash after `link_file_with_project` commits `index_status="pending"`
  blocks search forever (`ProjectIndexNotReady`, no stale-pending sweep); with
  `project_ids=None` one stuck file blocks search across all projects.
- `date.today()` (:64) and direct `datetime.now(UTC)` in ingestion bypass the
  aware-UTC timing helpers.

### 22. Thinking wiring keyed on model-name substring — `pipelines/inference.py:39-62`
`_thinking_payload_fields` matches `"qwen3"` inside the configured model
alias: any renamed GGUF/fine-tune alias silently loses BOTH thinking-off
control and reasoning separation — thinking stays on by template default
exactly on constrained calls (titles, future router classification). Resolve
the family once from config or the server's `/props`; warn when thinking-off
is requested and no wiring matches.

### 23. Embedding model drift between delivery shapes — `docker-compose.yml:80`,
`configs/models.yaml`
Docker downloads `Qwen/...Q8_0`; the desktop catalog downloads
`PeterAM4/...Q6_K` — same alias, different embedding spaces. Switching shapes
silently mixes spaces; the `VectorIndexMeta` fingerprint (model + dim) cannot
distinguish them. Align on one repo/quant or fold the file name into the
fingerprint.

### 24. Generation wire-contract gaps — `services/chatting.py`, `web/entities/thread.ts`
- No error/status terminal event: FAILED runs end with plain `done`
  (`StreamingBlock` has no error kind; entities keep `'error'` commented
  out), so failures render as empty successes.
- `start_generation` commits the user message before `_launch`: a
  journal/reserve failure 500s with the message persisted — resending
  duplicates it.

## Low

### 11. Dead Telegram-era code (~150 lines)
`routes/auth/views.py:154-168`,
`services/auth.py:118-142`, `services/connection.py`, commented `extract_service_token`
(`utils/web.py:108-118`), commented CORS block (`app.py:58-71`). Remove.

### 12. Transaction ownership — `save_message`
Commits internally (`chatting.py:66`) and callers commit again — violates the
"commit in services only" rule and hides who owns the boundary.

### 13. Dual dependency manifests
`pyproject.toml` (ranges) vs `requirements.txt` (pins, used by `Dockerfile.api`) —
guaranteed drift; nothing verifies pins satisfy ranges. Export from lock in CI.
Additionally `configs/inference.yaml` is read by nothing while `-ngl 40` is hardcoded
(`scripts/llama_launcher.py:45`); wire profiles in or delete the file until Phase 6.3.

### 14. Windows-path regex — `scripts/build_db_url.py:9`
Pattern only matches forward slashes; `\w` rejects hyphens/spaces. A
`DESKTOP_DB_PATH=.\data\clyre.sqlite3` silently produces a malformed URL. Also
`DB_RUNTIME=aiosqlite` default combines into an invalid `postgresql+aiosqlite://...`
driver when `DB_ENGINE=postgresql` — derive runtime per engine.

### 15. Misc frontend issues
- No single-flight refresh (see #9); dangling optimistic user message when access token
  missing (`pages/index.vue:231-234`).
- Frozen `isMobile = ref(display.mobile)` kills responsiveness on resize
  (`pages/index.vue:167`, `PromptBar.vue:48`).
- Blank chat screen with no loading/error state on deep-link before metadata loads
  (`pages/chat.vue:10-12`).
- highlight.js themes loaded from cdnjs at runtime — contradicts offline desktop
  (`PrettyMarkdown.vue:18-21`).
- Stray `console.log`s incl. `VITE_API_URL` leak (`utils/api.ts:7`), debug click handler
  (`pages/index.vue:49`), broken class concat `"position-relativepx-5"`
  (`pages/index.vue:94`).
- `watch` on the messages getter fires only on reference change — no autoscroll
  while stream chunks append (`pages/chat.vue:16-19`).
- 60 s threads-meta interval has no catch — backend down means an unhandled
  rejection every minute (`pages/index.vue:203`).
- `VITE_API_URL` absent from env docs (runtime falls back to `/api`).

### 16. Misc backend issues
- Unbounded `await upload.read()` — no size cap on uploads (`routes/files/views.py:37`);
  add streaming limit + content-type allowlist.
- Auth hardening gaps: no login rate limiting (matters on team server), email
  enumeration via register error message, refresh cookie without `secure=`/`samesite=`.
- `alembic/env.py:83`: URL with `%` breaks configparser interpolation (escape as `%%`);
  migration connections don't load sqlite-vec / FK pragma → autogenerate sees `vec0`
  shadow tables.
- Engine built at import time (`app.py:82`) — import side effects; move into startup.
- `getattr(raw, "_conn", raw)` pokes private aiosqlite attr (`db.py:27`).
- File store: direct write instead of temp+rename (`pipelines/fs/store.py:40`); no path
  containment check despite comment claiming defense-in-depth.
- duplicate modules `schemas/file.py` vs `schemas/files.py`;
  per-module `Logger.setLevel(DEBUG)` fights central logging config.

### 18. Default-thinking generations can exhaust context before any content —
`services/chatting.py` (`_launch`), `pipelines/inference.py`
With `enable_thinking` unset, no `chat_template_kwargs`/`reasoning_format` are
sent and Qwen3.5 thinks by default; on open-ended prompts (e.g. "write a long
story") the model can spend the whole 4096-token slot on reasoning and emit
zero content — the run then finishes "successfully" with an empty response and
thinking-only partials (observed live in e2e: 3974 thinking chunks, 0 content
chunks). There is no `max_tokens`/thinking-budget guard on the wire. Consider
capping generation length per request and/or surfacing empty-content runs as
failed.

### 17. Offset re-subscribe unreachable over HTTP — `routes/chatting/views.py`
`POST /api/chat/stream` always calls `start_generation`, so a client that
disconnects mid-stream cannot re-attach to the active run: the second request
hits `GenerationConflict` (409) and would even duplicate the user message.
The `offset` replay of `GenerationRun.subscribe` is therefore only reachable at
the service level today (covered by `tests_e2e/test_generation_pubsub.py`). A
dedicated attach/re-subscribe endpoint is needed for true reconnect semantics.

### 25. PLAN §6.3 claims undelivered work — `PLAN.md:320`
Checked desktop-packaging item describes a PyInstaller spec, generated and
persisted secrets, browser opening, and a clean-Windows test — none exist
(contradicts M11, unchecked). Rescope the box to what shipped.

### 26. Env template incomplete; empty secrets accepted — `configs/base.env.example`,
`shared/pyutils/env.py`
~10 live vars missing from the template (`*_BIND_HOST/_BIND_PORT`, token
durations, `VECTOR_DB_URL`, `NORMALIZE_VECTORS`, `CHUNK_*`); empty
`HASHING_SECRET`/`ACCESS_TOKEN_SECRET` satisfy Settings (compose enforces
`${VAR:?}`, desktop does not). Document the rest; add `min_length=1`.

### 27. e2e stack hygiene — `docker-compose.e2e.yml`, `tests_e2e/`
No healthchecks and 0.0.0.0 port publishes (an unauthenticated llama pair and
trivial-credential Postgres exposed LAN-wide during runs); conftest connects
without a retry; registration depends on internet (DNS MX check → the
gmail.com workaround); conflict tests burn slow LONG_PROMPT generations just
to keep a run alive; `test_chat_stream.py:309` pokes httpx private
`_transport`.

### 28. False-confidence unit tests — `tests/test_chat_stream.py`
- `test_disconnect_does_not_stop_generation` is vacuous: ASGITransport
  buffers the whole body, so no real disconnect ever reaches the app (same
  root cause as the e2e ASGITransport bug). Needs a real-socket (uvicorn)
  harness or an ASGI wrapper cancelling mid-stream.
- `flush_partial` failure and partial-content-then-FAILED paths are uncovered.
- Timing-based sync with ~50 ms margins is flaky on loaded runners; prefer
  event-gated fakes.
