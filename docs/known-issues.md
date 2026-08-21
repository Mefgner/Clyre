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

## Low

### 11. Dead Telegram-era code (~200 lines)
`routes/chatting/views.py:78-132`, `routes/auth/views.py:154-168`,
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
- `.gitignore` lacks `data/`; duplicate modules `schemas/file.py` vs `schemas/files.py`;
  per-module `Logger.setLevel(DEBUG)` fights central logging config.
