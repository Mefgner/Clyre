# Clyre — Declarative Development Plan

This plan describes what the finished thesis project looks like. It is a target state, not a sprint board.

The orchestrator is built **bottom-up**: the spine (L0+L1) is barely more than the current chat; the heavy machinery (L2) is a later, separable phase. Each cross-cutting feature has an explicit trigger — build it when the need is real, not before.

---

## Milestones

A milestone is a capability check: can Clyre do X, end to end, on local hardware.
Checked in order; each maps to the phase that makes it possible.

- [ ] **M1 — Boot.** On a clean machine, both `llama-server` processes start (chat + embedding) and the web app serves an authenticated chat. *(Phase 1)*
- [ ] **M2 — Fast chat.** A question is answered in `fast` mode with streaming, from a local model. *(Phase 2)*
- [ ] **M3 — Attached files.** A user uploads a file, attaches it to a thread, and the answer uses its full content at a stable position. *(Phase 2)*
- [ ] **M4 — Compaction.** A thread overflowing the context window is summarized (oldest → summary, recent verbatim) and still answers; the user is notified. *(Phase 2)*
- [ ] **M5 — Inline tool.** In `fast` mode the model makes one read-only tool call (fetch/search) and answers from the result. *(Phase 2)*
- [ ] **M6 — Projects.** A project groups threads and explicitly linked files can be selected from a listing. *(Phase 3)*
- [ ] **M7 — Project RAG.** A file is added to a project, indexed in the background, semantic search returns relevant chunks, and the answer uses them. *(Phase 4)*
- [ ] **M8 — Plan-and-execute.** A `plan` query runs planner → sequential steps → synthesizer and streams progress over SSE. *(Phase 5)*
- [ ] **M9 — Approval.** A write tool pauses at a human-in-the-loop gate; approve executes, reject fails. *(Phase 5)*
- [ ] **M10 — Benchmark.** Same queries on OpenCode (agentic) vs Clyre (deterministic), measured: tokens, LLM calls, latency, failure rate. *(Phase 6)*
- [ ] **M11 — Desktop packaging.** A clean Windows machine without Python installs and runs the packaged app. *(Phase 6)*

---

## Phase 1 — Structural foundation

Table stakes for the thesis evaluation. Without it the architecture is not defensible.

### 1.1 Alembic migrations
- [x] Add `alembic` to `pyproject.toml`
- [x] `alembic init` with async-compatible `env.py`
- [x] Initial migration from current models
- [x] Remove `init_models()` from `app.py` startup

### 1.2 Token revocation (minimal)
- [ ] `revoked_tokens` table: `jti` (UUID), `expires_at`
- [ ] On `/logout`, write the access token `jti`
- [ ] `extract_access_token` checks `jti` against the table
- [ ] Startup cleanup of expired rows

### 1.3 SQLite hardening
- [x] Enable WAL mode for the desktop SQLite engine (concurrent family writes)

### 1.4 Inference pipeline rename + dual model + model registry
- [ ] Rename `api/pipelines/llama.py` → `inference.py`, `LlamaLLMPipeline` → `OpenAICompatiblePipeline`
- [ ] `chat_completion_*` accept `content` as `str | list` (multimodal)
- [ ] Add constrained-decoding support (`response_format` / grammar) for structured outputs
- [ ] Env, three model tiers: `SMALL_*` (chat + worker steps), `BIG_*` (planner + synthesizer), `EMBEDDING_*` (a different model kind; needed only for RAG). Fallback: if only one of SMALL/BIG is set, it takes all load; EMBEDDING unset → RAG features off, chat works. Keep old `LLAMA_*` as deprecated aliases with a warning; rename `PRIMARY_*`/`SYNTHESIS_*` in `docker-compose.yml` and `env.py` accordingly
- [ ] `OpenAICompatiblePipeline` resolves the endpoint by role; one client class, three configured instances
- [ ] Fix `wait_for_startup` — max retry count (60 × 5s), raise after
- [ ] `scripts/llama_launcher.py` — launch `llama-server` per local tier: by default **two** (small 6760, embed 6761); a third only if `BIG_BASE_URL` points at a local process
- [ ] `configs/models.yaml` — replace Qwen3-4B with Qwen3.5-9B (Q4_K_M); add Qwen3-Embedding-0.6B
- [ ] `configs/inference.yaml` — drop 4GB/6GB; profiles for 8/12/16/24GB tuned for Qwen3.5-9B
- [x] Set `VECTOR_DIM = 1024` (Qwen3-Embedding-0.6B native)

---

## Phase 2 — L0/L1: the response spine

### 2.1 Retrieval functions (`api/services/retrieval.py`)
Plain async functions, callable by both the chat path and the orchestrator.
- [ ] `fetch_file(file_id) -> str`
- [ ] `list_project_files(project_id) -> list[FileMeta]`
- [x] `search_project(query, user_id, project_ids?, k) -> list[ChunkResult]` (validates owned scopes, delegates to `VectorRepository`)
- [ ] `hydrate_chunks(results) -> list[ChunkText]` — `ChunkResult` carries offsets, not text

### 2.2 File system abstraction (`api/pipelines/fs/`)
- [x] `FileStore` protocol: `save` / `read` / `delete`
- [x] `LocalFileStore` → `./data/files/<user_id>/<file_id>`
- [x] Resolved via `get_file_store()` (module-level singleton, same shape as the other pipelines)

### 2.3 File upload + linking endpoints (`api/routes/files/`)
Detailed steps: `docs/plans/vector-write-path.md`.
- [x] `POST /api/files/upload` — save file (`project_id = NULL` by default)
- [x] `GET /api/files/` — list user's files
- [x] `DELETE /api/files/{file_id}` — purge vectors explicitly, then delete row + blob
- [x] `POST /api/files/{file_id}/link/thread/{thread_id}`
- [x] `POST /api/files/{file_id}/link/project/{project_id}`
- [x] `crud/file.py` is implemented
- [x] Add `python-multipart` (FastAPI `UploadFile` requires it)

### 2.4 Summarization + chat compaction
- [ ] `api/pipelines/summarize.py`: `summarize(text, target_tokens) -> str`; token counts via `/tokenize`
- [ ] `ALLOW_FILE_SUMMARIZATION` env (default `true`)
- [ ] In `ChattingService`: track thread token count; on overflow summarize oldest messages, keep recent verbatim
- [ ] Emit `context_compacted` so the frontend notifies the user

### 2.5 L0 — fast path with attached files
- [ ] In `ChattingService.stream_response`: build context from history (compacted) + thread/project-attached files, injected at a **stable position** (never mid-history)
- [ ] No automatic RAG injection; files enter context only when attached or tool-fetched

### 2.6 L1 — single inline read-only tool call
- [ ] Allow the model (constrained output) to emit one read-only tool call in the fast path
- [ ] Execute via the retrieval functions → feed result back → continue generating
- [ ] Write tools are **not** allowed on the fast path (they force the plan path / approval)

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
retrieves from user-owned project scopes. Full implementation plan: **`docs/plans/vector-write-path.md`**.

### 4.1 Vector storage abstraction — done
- [x] Nullable `project_id` on `FileMetadata`
- [x] `VectorRepository` protocol: `ensure_schema` / `add_chunks` / `delete_by_file` / `search_similar_chunks`
- [x] `PgVectorRepository` (pgvector `<=>`, HNSW index)
- [x] `SqliteVecRepository` (sqlite-vec `vec0` virtual table, extension loaded in `db.register_sqlite_vec`)
- [x] Selected by `DB_ENGINE`; `ensure_schema` runs as an `app.py` startup handler
- [x] `VectorIndexMeta` + `services/embedding_space.py` — guards against mixing embedding spaces

### 4.2 Ingestion + embedding
- [x] `api/pipelines/ingest.py`: `extract_text` (text formats) + `chunk_text` with character offsets
- [ ] Add a shared document extraction layer before chunking: `DocumentExtractionResult` with normalized LLM-readable Markdown/plain text, preserved headings, paragraphs, tables, page/section boundaries, and source metadata; deterministic only, no LLM call
- [ ] Add format adapters and dependencies for PDF (`pypdf`), DOCX (`python-docx`), XLSX (`openpyxl`), and PPTX (`python-pptx`); unsupported formats must fail explicitly with a user-visible status
- [ ] Use the same extraction layer for file previews, attached-file context, and project ingestion so all paths see identical normalized content
- [x] `api/pipelines/embed.py`: `EmbeddingPipeline.embed` via the embedding `llama-server`; Matryoshka truncation + optional normalization
- [x] `api/services/ingestion.py` — the write path (`ingest_file`, `index_file_for_project`, `purge_file_vectors`); calls `ensure_for_write`
- [x] `ChunkVector.token_count` via llama-server `/tokenize` (`count_tokens_many` on `LlamaLLMPipeline`)
- [x] Deleting chunks must call `repository.delete_by_file` **explicitly** — the vector store sits outside the ORM, so no cascade reaches it. On SQLite the orphans consume `k` slots and silently degrade recall
- [x] `CHUNK_SIZE` / `CHUNK_OVERLAP` in settings (defaults `1500` / `200`)
- [x] `VECTOR_DIM` default is `1024`, matching Qwen3-Embedding-0.6B native dimension
- [x] Markdown/text extraction
- [ ] Image extraction/OCR or local multimodal fallback — later
- [ ] Add fixture tests for every supported document format, malformed files, empty documents, tables, and Unicode content

### 4.3 Promotion + search
- [x] `POST /api/files/{file_id}/link/project/{project_id}` — set `project_id`, schedule ingestion + embedding
- [x] `search_project` wired through `VectorRepository`, validates the embedding space on read
- [ ] Available as a tool on the plan path (and optionally L1)

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

## Phase 5 — L2: the orchestrator (Plan-and-Execute)

Build only after L0/L1 are solid. **Not** ReAct — finite plan, no open loop.

### 5.1 Engine core
- [ ] `OrchestratorState` (JSON-serializable): run_id, plan, step outputs, status, history
- [ ] `Step`: id, tool, input (may hold `$stepN.field` refs), status, output
- [ ] `engine.py`: sequential step execution; engine resolves `$stepN` refs before each call
- [ ] `planner.py`: full context → finite list of steps (runs on `BIG`, falls back to `SMALL`)
- [ ] `synthesizer.py`: full context + step results → answer (runs on `BIG`)
- [ ] Worker steps run on `SMALL`; only planner/synthesizer use the `BIG` reasoning tier
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

### 5.6 Endpoints + router
- [ ] `POST /api/agent/run` → enqueue, return `run_id`
- [ ] `GET /api/agent/{run_id}/stream` → SSE from in-memory pub/sub; coarse status from snapshot if not in RAM
- [ ] `GET /api/agent/{run_id}` → status + final snapshot (reload/history)
- [ ] `api/services/router.py` — fast-vs-plan classifier (constrained one-token output); mode `auto|fast|plan`. **MVP may ship a manual toggle and defer auto-classification.**
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
- [ ] 4B vs 9B on structured output / tool calling; demonstrate why 9B is the floor
- [ ] Scalability test: concurrent users, streaming throughput, SQLite WAL write concurrency
- [ ] Edge-device performance: run the benchmark on a consumer GPU, report latency / tokens / VRAM / failure rate

### 6.3 Deployment
Runtime-agnostic monolith, two delivery shapes over the same code (see ADR-3): desktop script vs Docker Compose.
- [ ] Pin a tested llama.cpp build (version + sha256 in `configs/binaries.yaml`) and host the zip as a GitHub Release asset in this repo; first-run downloads from there, not upstream — reproducible install, fixed benchmark runtime, no upstream drift
- [ ] Desktop (household): `run-desktop.py` / PyInstaller spec (`api/`, `scripts/`, `shared/`, `dist/`, `configs/`); first-run downloads the pinned binaries + Qwen3.5-9B (~5.5GB) + Qwen3-Embedding-0.6B → starts llama-server(s) + uvicorn → opens browser; SQLite + sqlite-vec by default; test on a clean Windows machine without Python
- [ ] Team server (Docker Compose): `docker compose up` — `db` (PostgreSQL + pgvector) + `clyre` (FastAPI monolith + Vue static); llama-server runs natively on the host for direct GPU (container reaches it via `host.docker.internal`) or as a compose service where nvidia-container-toolkit is configured; teammates reach it over the LAN in a browser (JWT multi-user already in scope)
- [ ] Persist uploaded files in the team Docker deployment: mount `FILES_DIR` to a named volume or host path, and document backup/restore together with the database
- [ ] Optional headless team mode without Docker: the desktop script as a systemd unit (Linux) / Windows service — always-on, auto-start on boot

### 6.4 Frontend completeness
- [ ] File management UI (upload, list, attach, index automatically in project)
- [ ] Project sidebar
- [ ] Agent progress stepper with approval dialog
- [ ] Settings: inference/embedding URLs, model names, `ALLOW_FILE_SUMMARIZATION`, router mode
- [ ] PWA: manifest + service worker + icons (`vite-plugin-pwa`) — installable, standalone window, offline shell; works on `localhost` (desktop); on LAN it degrades to a browser tab without a self-signed cert

### 6.5 Observability
- [ ] Structured request logging (request id, user id, duration)
- [ ] `/api/metrics`: token usage, active threads, model status, compaction count

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
