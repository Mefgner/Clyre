# Clyre — Declarative Development Plan

This plan describes what the finished thesis project looks like. It is a target state, not a sprint board.

The orchestrator is built **bottom-up**: the spine (L0+L1) is barely more than the current chat; the heavy machinery (L2) is a later, separable phase. Each cross-cutting feature has an explicit trigger — build it when the need is real, not before.

> **Routing pivot.** The model never sees raw tools: fast mode is a deterministic router over
> fixed-topology capability pipelines (see `docs/plans/tool-contract.md` and ADR-draft 11).
> Phase 5 (plan-and-execute, approval) is deferred post-thesis; its design is kept for
> forward compatibility of the tool contract.

---

## Milestones

A milestone is a capability check: can Clyre do X, end to end, on local hardware.
Checked in order; each maps to the phase that makes it possible.

- [x] **M1 — Boot.** On a clean machine, both `llama-server` processes start (chat + embedding) and the web app (built frontend served by FastAPI, SPA fallback) serves an authenticated chat. *(Phase 1)*
- [x] **M2 — Fast chat.** A question is answered through the single streaming chat path, from a local model. *(Phase 2)*
- [x] **M3 — Attached files.** A user uploads a file, attaches it to a thread, and the answer uses its full content at a stable position. *(Phase 2)*
  - Accepted on local hardware in desktop test mode with Qwen3.5-4B Q3:
    non-thinking generation used the uploaded file in the first answer and
    continued the conversation with the file remaining in thread context.
    Automated backend, frontend, and regular live E2E suites pass.
- [ ] **M4 — Compaction.** A thread overflowing the context window is summarized (oldest → summary, recent verbatim) and still answers; the user is notified. *(Phase 2)*
- [ ] **M5 — Routing.** The fast-mode router classifies a query into plain chat or a registered read-only capability; the capability pipeline runs end to end and the answer uses its result. *(Phase 2)*
- [ ] **M6 — Projects.** A project groups threads and explicitly linked files can be selected from a listing. *(Phase 3)*
- [ ] **M7 — Project RAG.** A file is added to a project, indexed in the background, semantic search returns relevant chunks, and the answer uses them. *(Phase 4)*
- [ ] **M8 — Plan-and-execute** *(deferred, post-thesis)*. A `plan` query runs planner → sequential steps → synthesizer and streams progress over SSE. *(Phase 5)*
- [ ] **M9 — Approval** *(deferred, post-thesis; enforcement of `access: W`)*. A write tool pauses at a human-in-the-loop gate; approve executes, reject fails. *(Phase 5)*
- [ ] **M10 — Benchmark.** Same queries on OpenCode (agentic) vs Clyre (deterministic), measured: tokens, LLM calls, latency, failure rate. *(Phase 6)*
- [ ] **M11 — Desktop packaging.** A clean Windows machine without Python installs and runs the packaged app. *(Phase 6)*

> **Environment boundary.** Source and Docker installations require the user to
> create and configure `.env` manually from `configs/base.env.example`, including
> the required secrets. M1 does not generate secrets automatically. First-run
> secret generation and persistence are reserved for the packaged EXE in M11.

---

## Phase 1 — Structural foundation

Table stakes for the thesis evaluation. Without it the architecture is not defensible.

### 1.1 Alembic migrations
- [x] Add `alembic` to `pyproject.toml`
- [x] `alembic init` with async-compatible `env.py`
- [x] Initial migration from current models
- [x] Remove `init_models()` from `app.py` startup

### 1.2 Authentication and token revocation
- [x] Access JWTs are signed with `ACCESS_TOKEN_SECRET`, carry a standard `exp` claim,
  `user_id`, and the related `refresh_token_id`
- [x] `refresh_token` table: `id`, `token_hash`, `user_id`, `created_at`, `expires_at`, `revoked_at`
- [x] Refresh cookies contain opaque random tokens; only their SHA-256 hashes are stored
- [x] `/refresh` rotates the refresh token: revokes the old row and creates a new one
- [x] `/logout` revokes the current refresh-token row and clears the httponly cookie
- [x] `extract_access_token` checks the linked refresh-token row, expiry, revocation, and user ownership
- [x] JWT security coverage: signature tampering, wrong secret, unsupported algorithms, expiration,
  malformed claims, cross-user token references, and refresh-token type confusion

### 1.3 SQLite hardening
- [x] Enable WAL mode for the desktop SQLite engine (concurrent family writes)

### 1.4 Inference pipeline rename + dual model + model registry
- [x] Rename `api/pipelines/llama.py` → `inference.py`, `LlamaLLMPipeline` → `LLMPipeline`
- [x] `chat_completion_*` accept `content` as `str | list` (multimodal)
- [x] Add constrained-decoding support (`response_format` / grammar) for structured outputs
- [x] Env exposes two model endpoints: `CHAT_*` for every cognitive role and
  `EMBEDDING_*` for RAG. The earlier `SMALL_*` / `BIG_*` split was removed outright (no
  deprecated aliases) by ADR-12 because a separate large model contradicts the edge target
- [x] One `LLMPipeline` instance serves the chat endpoint; embedding stays a separate
  `EmbeddingPipeline`. Role-specific behavior is expressed through call parameters and,
  when needed, logical profiles rather than physical model tiers
- [x] Fix `wait_for_startup` — max retry count (60 × 5s), raise after (both `inference.py` and `embed.py`)
- [x] `scripts/llama_launcher.py` launches exactly two local `llama-server` processes:
  chat on 6760 and embedding on 6761
- [x] `configs/models.yaml` — replace Qwen3-4B with Qwen3.5-9B (Q4_K_M); add Qwen3-Embedding-0.6B (Q6_K). Model catalog is the source of truth (`role:` field); `.env` holds only route overrides. The catalog contains only fields needed for download, selection and launch.
- [x] `configs/inference.yaml` — drop 4GB/6GB; profiles for 8/12/16/24GB tuned for Qwen3.5-9B
- [x] Set `VECTOR_DIM = 1024` (Qwen3-Embedding-0.6B native)

### 1.5 Environment template
- [x] `configs/base.env.example` filled with a working manual template (required
  `HASHING_SECRET` / `ACCESS_TOKEN_SECRET` left empty for the user to set)
- [x] Documented (in the template and the M1 note) that `.env` is user-managed in
  source/Docker mode; required secrets are supplied manually and never generated
  by M1 bootstrap
- [x] Remove `configs/base.env`; keep only `configs/base.env.example`
- [x] Reserve automatic local secret generation and persistence for the packaged
  EXE first-run flow in M11 (noted in 6.3)

### 1.6 Static web serving (FastAPI)
- [x] FastAPI serves the built frontend for both delivery shapes with SPA fallback
  to `index.html`; API routes stay under `/api` and are unaffected
  (`api/app.py` finds the build under `web/dist` or `dist`)
- [x] Desktop: `run-desktop.py` boots uvicorn that serves the built frontend on the
  same origin as the API — no Node/nginx needed at runtime
- [x] Docker: the web build is baked into the API image (multi-stage `Dockerfile.api`)
  and served by FastAPI; `nginx.conf` and the separate `web` service removed
- [x] Vite dev-server proxy `/api` → `localhost:6750` for the dev flow
- [x] First-run/readme documents `npm ci` + `npm run build` before boot for source
  installs; the packaged EXE embeds the built frontend

---

## Phase 2 — L0/L1: the response spine

### 2.1 Retrieval functions (`api/services/retrieval.py`)
Plain async functions, callable by both the chat path and the orchestrator.
- [x] `fetch_file(file_id) -> str` (M3: strict shared `extract_text`, not lossy decode)
- [x] `list_project_files(project_id) -> list[FileMeta]`
- [x] `search_project(query, user_id, project_ids?, k) -> list[ChunkResult]` (validates owned scopes, delegates to `VectorRepository`)
- [x] `hydrate_chunks(results) -> list[ChunkText]` — `ChunkResult` carries offsets, not text

### 2.2 File system abstraction (`api/pipelines/fs/`)
- [x] `FileStore` protocol: `save` / `read` / `delete`
- [x] `LocalFileStore` → `./data/files/<user_id>/<file_id>`
- [x] Resolved via `get_file_store()` (module-level singleton, same shape as the other pipelines)
- [x] Hardened (M3): component allowlist + resolved containment under the store root and
  the user dir on every op; never interpolates the original filename; atomic
  temp-file + `os.replace` writes with temp cleanup on failure

### 2.3 File upload + linking endpoints (`api/routes/files/`)
- [x] `POST /api/files/upload` — save file (`project_id = NULL` by default)
- [x] `GET /api/files/` — list user's files
- [x] `DELETE /api/files/{file_id}` — purge vectors explicitly, then delete row + blob
- [x] `POST /api/files/{file_id}/link/thread/{thread_id}`
- [x] `POST /api/files/{file_id}/link/project/{project_id}`
- [x] `crud/file.py` is implemented
- [x] Add `python-multipart` (FastAPI `UploadFile` requires it)
- [x] Safe upload (M3): chunked read capped by `MAX_UPLOAD_BYTES` (10 MiB, → 413),
  MIME normalized without parameters, text-only allowlist (→ 415), strict UTF-8
  with BOM / NUL rejection (→ 422), empty files allowed, checks before any
  metadata/blob write, compensating blob delete on transaction failure
- [x] Thread attachments (M3): `GET /api/thread/{thread_id}/files`,
  `DELETE /api/files/{file_id}/link/thread/{thread_id}` (idempotent 204);
  `DELETE /api/files/{file_id}` deletes metadata first and the blob after a
  successful commit (cleanup failures logged, never strand a live row)

### 2.4 Summarization + chat compaction
- [ ] `api/pipelines/summarize.py`: `summarize(text, target_tokens) -> str`; token counts via `/tokenize`
- [ ] `ALLOW_FILE_SUMMARIZATION` env (default `true`)
- [ ] In `ChattingService`: track thread token count; on overflow summarize oldest messages, keep recent verbatim
- [ ] Emit `context_compacted` so the frontend notifies the user

### 2.5 L0 — fast path with attached files
- [x] In `ChattingService.stream_response`: build context from history (compacted) + **thread**-attached files, injected at a **stable position** (never mid-history) — M3: pure `build_chat_context` (one system message with a JSON `attached_files` block marked untrusted, history, current exactly once), Python-side `(name, id)` ordering, strict `extract_text` for every attached byte, never `head_value`
- [ ] Project-attached files in context (waits for the M6 project UI; project membership alone adds nothing today)
- [x] No automatic RAG injection; files enter context only when attached or tool-fetched
- [x] Strict token budget (M3): full prompt rendered through the server chat template (`/apply-template` with the same thinking params as generation), counted via `/tokenize`, checked against the real slot size (`/props`); admit only `prompt_tokens + CHAT_MAX_OUTPUT_TOKENS (1024) <= slot`, same reserve sent as `max_tokens`; overflow → 422 `context_limit_exceeded`, unavailable preflight → 503 (never approximate)
- [x] Atomic generation start (M3): `fileIds` in the chat request; prepare (ownership → union ≤ 16 → sequential read → context → budget → title) before any write; one commit for thread/links/user message/journal/reserve; prepare failure creates nothing and calls neither completion nor title; retry prepares before deleting the previous answer; legacy `/response` wraps the same start path

### Post-M3 file relevance window (agreed direction, not implemented)
- Attaching a file, or explicitly invoking it, opens a window of 5 user requests.
- Automatic relevance checking ahead of the router does not extend the window.
- After the window the file is used only on explicit user reference.
- A relevant file is passed whole when it fits; otherwise a separate sequential
  pipeline processes its chunks and returns results with sources.
- Bounding/merging of intermediate results is defined during that capability's
  planning together with M5.

### 2.6 Fast-mode routing (replaces the inline-tool-call design)
Full contract: **`docs/plans/tool-contract.md`** — categories, manifest, skeleton, ranking,
durability, router mechanics. The model never sees raw tools; selection is deterministic.
- [ ] `@plugin` registry (`api/modules/engine/plugins/`) + dynamic name list for the router
- [ ] Router: one constrained chat-model classification per message (recent history + registry names) → `chat` | `<plugin>`; multi-intent → plugin priority + honest disclaimer
- [ ] Thin tools (`fetch_file`, `list_project_files`, `search_project`) stay code-only building blocks for handlers
- [ ] First thick plugin proves the skeleton (file-oriented capability first; `web_search` follows once its data-source backend is chosen)
- [ ] Runtime-owned file mutation gateway enforces approved `lock → durable intent → atomic apply → commit → unlock`, hash-based conflict detection/recovery, and forbids direct writes from `W|RW` handlers
- [ ] Re-entry refinement: parse merges delta over snapshot params; param diff → re-synthesize vs re-collect

### 2.7 Resilient generation
Generation is decoupled from the client connection: an in-memory run registry per
thread owns the inference task; clients are subscribers with an offset.
- [x] `api/services/generation.py`: `GenerationRun` (asyncio task, event buffer,
  subscriber queues, status `running|finished|stopped|failed|interrupted`); module-level
  registry `{thread_id: run}`; disconnect kills only the subscriber, never the task
- [x] `GET /api/chat/stream/{thread_id}?offset=N` replays buffered events from the
  exact offset, then goes live without starting a second generation
- [x] Durable call journal: `generation_run` table (id, thread_id, user_id, status,
  `side_effects`, timestamps); assistant message row reserved upfront, partial content
  flushed periodically (~1s), finalized at terminal state; startup sweep marks orphaned
  `running` rows `interrupted`; `is_generating` exposed in thread metadata
- [x] **Retry policy** (fixed): live reconnect → true resume from offset over HTTP.
  Server crash →
  retry only while `side_effects=False` (fast chat has none by construction); once a W/RW
  effect has been recorded, retry is forbidden — keep the partial answer and continue the
  dialog on top. True retry-from-checkpoint arrives with Phase 5 approval gates
  (`PLAN-NOTE(2.7)` at the `side_effects` field)
- [x] Send during an active generation → 409 (frontend disables Send until terminal);
  Stop cancels the task and persists the accumulated partial as the final message
- [ ] `pipeline_run` stage-boundary snapshots (L1 durability): crash recovery and citation
  metadata; seed of the deferred checkpoint model — extends `generation_run`, post-M2

---

## Phase 3 — Project management

### 3.1 Project file listing
- [ ] `list_project_files` returns explicitly linked files with name, content type and `head_value`

### 3.2 Endpoints
- [x] `POST /api/projects/` — create
- [x] `GET /api/projects/` — list
- [x] `PUT /api/projects/{project_id}` — update title
- [x] `DELETE /api/projects/{project_id}` — delete (cascades to threads and purges index)
- [ ] `POST /api/projects/{project_id}/threads/{thread_id}` — assign thread
- [ ] Frontend: project sidebar, thread grouping

---

## Phase 4 — Project scope (embedding retrieval)

The only level where RAG applies. Triggered when a file is added to a **project's** index.

**Scope model.** RAG is per-project: indexed chunks carry their `project_id`. No global or shared
index — a shared KB degrades into a dump too quickly to be useful, and a household has
no "knowledge base", it has files tied to the work at hand. The project corpus bounds the
index: deleting the project purges its vectors, and retrieval pays off exactly where
whole-file injection stops scaling (a project with dozens of large files fits no context
window). No membership table. `project_id` is the only index scope.
- [x] `search_similar_chunks` takes `project_ids: Sequence[str]`, not one id (pg: `IN`; sqlite: per-project `MATCH` + merge by distance, `vec0` metadata filtering is limited) — one user has several projects; hits merge across them
- [x] `retrieval.project_scopes(user_id)`; `search_project` takes `user_id`, never a raw project id from the client
- [x] Project linking schedules indexing — the server validates file and project ownership
- [x] Deleting a project or unpromoting a file must purge its vectors (no FK, nothing cascades)

The read and write paths are available through the file API — they connect
`extract_text → chunk_text → embed → ChunkVector + add_chunks`, and `search_project` now
retrieves from user-owned project scopes.

### 4.1 Vector storage abstraction — done
- [x] Nullable `project_id` on `FileMetadata`
- [x] `VectorRepository` protocol: `ensure_schema` / `add_chunks` / `delete_by_file` / `search_similar_chunks`
- [x] `PgVectorRepository` (pgvector `<=>`, HNSW index)
- [x] `SqliteVecRepository` (sqlite-vec `vec0` virtual table, extension loaded in `db.register_sqlite_vec`)
- [x] Selected from the live SQLAlchemy engine dialect (`DB_ENGINE`/`DATABASE_URL`
  configure the engine); `ensure_schema` runs as an `app.py` startup handler
- [x] `VectorIndexMeta` + `services/embedding_space.py` — guards against mixing embedding spaces

### 4.2 Ingestion + embedding
- [x] `api/pipelines/ingest.py`: `extract_text` (text formats) + `chunk_text` with character offsets
- [ ] Add a shared document extraction layer before chunking: `DocumentExtractionResult` with normalized LLM-readable Markdown/plain text, preserved headings, paragraphs, tables, page/section boundaries, and source metadata; deterministic only, no LLM call
- [ ] Add format adapters and dependencies for PDF (`pypdf`), DOCX (`python-docx`), XLSX (`openpyxl`), and PPTX (`python-pptx`); unsupported formats must fail explicitly with a user-visible status
- [ ] Use the same extraction layer for file previews, attached-file context, and project ingestion so all paths see identical normalized content
- [x] `api/pipelines/embed.py`: `EmbeddingPipeline.embed` via the embedding `llama-server`; Matryoshka truncation + optional normalization
- [x] `api/services/ingestion.py` — the write path (`ingest_file`, `index_file_for_project`, `purge_file_vectors`); calls `ensure_for_write`
- [x] `ChunkVector.token_count` via llama-server `/tokenize` (`count_tokens_many` on `LLMPipeline`)
- [x] Deleting chunks must call `repository.delete_by_file` **explicitly** — the vector store sits outside the ORM, so no cascade reaches it. On SQLite the orphans consume `k` slots and silently degrade recall
- [x] `CHUNK_SIZE` / `CHUNK_OVERLAP` in settings (defaults `1500` / `200`)
- [x] `VECTOR_DIM` default is `1024`, matching Qwen3-Embedding-0.6B native dimension
- [x] Markdown/text extraction
- [ ] Image extraction/OCR or local multimodal fallback — later
- [ ] Add fixture tests for every supported document format, malformed files, empty documents, tables, and Unicode content

### 4.3 Promotion + search
- [x] `POST /api/files/{file_id}/link/project/{project_id}` — set `project_id`, schedule ingestion + embedding
- [x] `search_project` wired through `VectorRepository`, validates the embedding space on read
- [ ] Exposed as the `find_in_project` capability through the tool contract (`docs/plans/tool-contract.md`)

### 4.4 Embedding-space migration
The embedder changes over the project's life; that is a first-class operation, not an error.
Dimension is fixed at `CREATE` on both backends (sqlite-vec `float[N]`, pgvector `Vector(N)`),
so a model change is always DROP + CREATE + full re-embed. **Not an Alembic concern** —
it is a data operation that needs a live `llama-server`.

Simplest defensible shape: **block startup until migration completes** — the app only
comes up with a ready index, so no intermediate state is ever visible. `run-desktop.py`
already starts the llama-server group before uvicorn; the migration slots in between.

Schema shape (ships with 4.2):
- [ ] `VectorRepository.recreate_schema(engine)` — `ensure_schema` alone silently keeps a table of the old dimension
- [ ] `PgVectorRepository` rebuilds its `Table` from current env instead of capturing `VECTOR_DIM` once in `__init__`
- [ ] `VectorIndexMeta`: fingerprint (`model` + `dim`) + `status` (`ready|failed`) — enough to detect a mismatch and to know the index is unusable
- [ ] E2E migration test for both SQLite/sqlite-vec and PostgreSQL/pgvector: build an old embedding space, change model/dimension, recreate the index, re-embed a file, verify search uses only the new vectors, and verify failure leaves the index unavailable rather than mixing spaces

Startup migration:
- [ ] On startup, compare the embedder fingerprint against `VectorIndexMeta`; on mismatch → `embedding_space.migrate()`: recreate store → re-ingest every indexed file, commit per file, idempotent on re-run (crash mid-way → next start resumes, not restarts)
- [ ] Print per-file progress to the console (`Rebuilding KB: 12/40 files`) — a silent migration reads as a hang
- [ ] Failure escape hatch: a failed rebuild must not loop the app — skip it, mark the index failed, and start anyway; L0 chat works, `search_project` → 409, never 500
- [ ] Block only migration, never staleness: if migration is disabled/not run, an old-dimension index does not block startup; search reports unavailable
- [ ] Re-ingest requires a healthy embedding `llama-server` — the bootstrap script sequences the migration after it is up
- [ ] Out of scope: zero-downtime migration, versioned side-by-side spaces, per-chunk lazy re-embed — distances from two embedding spaces cannot be merged into one ranking

---

## Phase 5 — L2: the orchestrator (Plan-and-Execute) — **deferred, post-thesis**

The fast-mode router (Phase 2) covers thesis-scope capabilities; plan-and-execute and
approval enforcement move to post-thesis work. Kept below as the target design so the tool
contract stays forward-compatible. Every cognitive role uses the same chat model; separate
call profiles may vary prompts and generation parameters. Build only after L0/L1 are solid.
**Not** ReAct — finite plan, no open loop.

### 5.1 Engine core
- [ ] `OrchestratorState` (JSON-serializable): run_id, plan, step outputs, status, history
- [ ] `Step`: id, tool, input (may hold `$stepN.field` refs), status, output
- [ ] `engine.py`: sequential step execution; engine resolves `$stepN` refs before each call
- [ ] `planner.py`: full context → finite list of steps on the chat model
- [ ] `synthesizer.py`: full context + step results → answer on the chat model
- [ ] Worker steps use isolated context; planner/synthesizer use full context. All roles
  share one model endpoint and may use distinct call profiles
- [ ] Verify: at most one capped re-plan on failure (never a loop)

### 5.2 Tool registry
- [ ] `ToolManifest`: name, description, input/output schema, handler, `requires_approval`
- [ ] Load from `configs/tools/*.yaml`; validate I/O against schemas
- [ ] Built-in tools (few, high-level): `fetch_file`, `list_project_files`, `search_project`
- [ ] A handler may wrap a deterministic sub-machine ("garbage → structured content"); hidden sub-machines are **read-only**
- [ ] Worker steps get **isolated** context; planner/synthesizer get full context

### 5.3 Agent manifests
- [ ] `AgentManifest` Pydantic model; load + validate `configs/agents/*.yaml` at startup; cache (`lru_cache`)

### 5.4 Persistent runs (checkpoint model)
- [ ] `agent_run` table: id, user_id, agent, input, status, `state_snapshot` (JSON), result, error, timestamps (migration). **No per-event table.**
- [ ] In-process worker (asyncio task from `lifespan`) reading an `asyncio.Queue`; sequential execution
- [ ] Checkpoint full snapshot only at: creation, approval, terminal
- [ ] In-memory pub/sub keyed by `run_id` for live SSE (no DB polling)
- [ ] Startup recovery: `running` rows with no RAM entry → `interrupted`; `waiting_approval` → re-armed

### 5.5 Human-in-the-loop approval
- [ ] Write tool with `requires_approval: true` → `approval_required` event + checkpoint `waiting_approval` + suspend on `asyncio.Event`
- [ ] `POST /api/agent/{run_id}/approve` | `/reject` → resume / fail
- [ ] Frontend approval dialog

### 5.6 Endpoints
- [ ] `POST /api/agent/run` → enqueue, return `run_id`
- [ ] `GET /api/agent/{run_id}/stream` → SSE from in-memory pub/sub; coarse status from snapshot if not in RAM
- [ ] `GET /api/agent/{run_id}` → status + final snapshot (reload/history)
- [ ] Frontend progress stepper driven by SSE

### 5.7 MCP (optional, if time permits)
- [ ] MCP servers register tools into the same registry; write tools flagged `requires_approval`

---

## Phase 6 — Polish & thesis packaging

### 6.1 Pagination
- [ ] `GET /api/thread/all` — `limit`/`offset`
- [ ] `GET /api/thread/{id}` — paginate messages

### 6.2 Thesis evaluation artifacts
- [ ] Passive top-k RAG vs agentic fetch on 3-5 queries; document the gap
- [ ] Retrieval quality ladder on a fixed corpus: R1 naive user query vs R2 model-written query (parse-node reformulation) vs R3 multi-query voting; recall/precision metrics (see `docs/plans/tool-contract.md`, Thesis link)
- [ ] 4B vs 9B on structured output / tool calling; demonstrate why 9B is the floor
- [ ] Thinking on/off benchmark: quality/latency trade-off of `enable_thinking` on fast-mode answers
- [ ] Scalability test: concurrent users, streaming throughput, SQLite WAL write concurrency
- [ ] Edge-device performance: run the benchmark on a consumer GPU, report latency / tokens / VRAM / failure rate

### 6.3 Deployment
Runtime-agnostic monolith, two delivery shapes over the same code (see ADR-3): desktop script vs Docker Compose.
- [x] Pin a tested llama.cpp build (version + sha256 in `configs/binaries.yaml`) — binary + cudart DLL set, both FLAT zips extracted into one `binaries/<folder>/` so `llama-server.exe` sits next to `ggml-cuda.dll` and the cudart libs; downloader/exe-resolution logic verified against the real archive layout
- [ ] Host the pinned zips as GitHub Release assets in this repo; first-run downloads from there, not upstream — reproducible install, fixed benchmark runtime, no upstream drift
- [x] Desktop source launcher: `run-desktop.py` downloads the pinned binaries +
  Qwen3.5-9B (~5.5GB) + Qwen3-Embedding-0.6B, then starts llama-server(s) + uvicorn
  serving the built frontend; SQLite + sqlite-vec by default
- [ ] Desktop packaged app: add the PyInstaller spec and bundle
  (`api/`, `scripts/`, `shared/`, `dist/`, `configs/`); generate and persist secrets on
  first run; open the browser; verify on a clean Windows machine without Python
- [x] Team server (Docker Compose): `docker compose up` — `db` (pgvector image) + `clyre` (FastAPI monolith serving the built Vue frontend); llama/embedding services with HF model auto-download and `/health` healthchecks; the API waits for db+llama+embedding to be healthy
- [ ] Docker: llama-server runs natively on the host for direct GPU (container reaches it via `host.docker.internal`) or as a compose service where nvidia-container-toolkit is configured — verify the GPU-reservation path on a real host
- [ ] Persist uploaded files in the team Docker deployment: mount `FILES_DIR` to a named volume or host path, and document backup/restore together with the database
- [ ] Optional headless team mode without Docker: the desktop script as a systemd unit (Linux) / Windows service — always-on, auto-start on boot

### 6.4 Frontend completeness
- [ ] File management UI (upload, list, attach, index automatically in project)
- [ ] Project sidebar
- [ ] Agent progress stepper with approval dialog
- [ ] Settings: inference/embedding URLs, model names, `ALLOW_FILE_SUMMARIZATION`
- [ ] Thinking toggle in the UI (backend support shipped with M2: `enableThinking` request flag, `new_thinking_chunk` NDJSON event, persisted `Message.thinking_value`; thinking is display-only — never re-sent in history per the Qwen3.5 model card)
- [ ] PWA: manifest + service worker + icons (`vite-plugin-pwa`) — installable, standalone window, offline shell; works on `localhost` (desktop); on LAN it degrades to a browser tab without a self-signed cert

### 6.5 Observability
- [ ] Structured request logging (request id, user id, duration)
- [ ] `/api/metrics`: token usage, active threads, model status, compaction count

### 6.6 Maintenance and security hardening
- [ ] Cleanup of expired/revoked refresh-token rows

---

## What is intentionally out of scope

- Tauri/Electron wrapper (browser on localhost is enough)
- Mobile clients
- Telegram bot (commented-out code — remove or leave commented)
- Cloud provider support (the OpenAI-compatible URL covers all local cases)
- nginx / TLS termination (the compose stack serves plain HTTP on the LAN; a self-signed cert for PWA install is a later option)
- Multi-tenancy / RBAC (RAG is per-project; `user_id` FK isolation suffices)
- Global/shared index (a shared dump degrades fast; per-project indexes only)
- Real-time collaboration (SSE is one-way and sufficient)
- Incremental chunk diffing on file update (re-ingest whole file)
- Separate vector database (pgvector + sqlite-vec; no Qdrant/Weaviate)
- ReAct / open-ended agent loops (finite plan only)
- Branching/DAG plans, parallel sub-agents (linear, sequential — one llama-server)
- Widget engine / dashboard (Future Work in the thesis text; its "processor" survives as a read-only tool)
