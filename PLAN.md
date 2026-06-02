# Clyre — Declarative Development Plan

This plan describes what the finished thesis project looks like. It is a target state, not a sprint board.

The orchestrator is built **bottom-up**: the spine (L0+L1) is barely more than the current chat; the heavy machinery (L2) is a later, separable phase. Each cross-cutting feature has an explicit trigger — build it when the need is real, not before.

---

## Phase 1 — Structural foundation

Table stakes for the thesis evaluation. Without it the architecture is not defensible.

### 1.1 Alembic migrations
- [ ] Add `alembic` to `pyproject.toml`
- [ ] `alembic init` with async-compatible `env.py`
- [ ] Initial migration from current models
- [ ] Remove `init_models()` from `app.py` startup
- [ ] Document migration workflow in `CLAUDE.md`

### 1.2 Inference pipeline rename + dual model + model registry
- [ ] Rename `api/pipelines/llama.py` → `inference.py`, `LlamaLLMPipeline` → `OpenAICompatiblePipeline`
- [ ] `chat_completion_*` accept `content` as `str | list` (multimodal)
- [ ] Add constrained-decoding support (`response_format` / grammar) for structured outputs
- [ ] Env, three model roles: `PRIMARY_*` (chat + workers), `SYNTHESIS_*` (planner + synthesizer; empty → falls back to PRIMARY), `EMBEDDING_*`. Keep old `LLAMA_*` as deprecated aliases with a warning
- [ ] `OpenAICompatiblePipeline` resolves the endpoint by role; one client class, three configured instances
- [ ] Fix `wait_for_startup` — max retry count (60 × 5s), raise after
- [ ] `scripts/llama_launcher.py` — launch `llama-server` per local role: by default **two** (primary 6760, embed 6761); a third only if `SYNTHESIS_BASE_URL` points at a local process
- [ ] `configs/models.yaml` — replace Qwen3-4B with Qwen3.5-9B (Q4_K_M); add Qwen3-Embedding-0.6B
- [ ] `configs/inference.yaml` — drop 4GB/6GB; profiles for 8/12/16/24GB tuned for Qwen3.5-9B
- [ ] Set `VECTOR_DIM = 1024` (Qwen3-Embedding-0.6B native)

### 1.3 SQLite hardening
- [ ] Enable WAL mode for the desktop SQLite engine (concurrent family writes)

### 1.4 Token revocation (minimal)
- [ ] `revoked_tokens` table: `jti` (UUID), `expires_at`
- [ ] On `/logout`, write the access token `jti`
- [ ] `extract_access_token` checks `jti` against the table
- [ ] Startup cleanup of expired rows

---

## Phase 2 — L0/L1: the response spine

### 2.1 Retrieval functions (`api/services/retrieval.py`)
Plain async functions, callable by both the chat path and the orchestrator.
- [ ] `fetch_file(file_id) -> str`
- [ ] `list_project_files(project_id) -> list[FileMeta]`
- [ ] `search_workspace(query, workspace_id, k) -> list[ChunkResult]` (delegates to `VectorRepository`)

### 2.2 File system abstraction (`api/pipelines/fs/`)
- [ ] `FileStore` protocol: `save(file_bytes, filename, user_id) -> str`
- [ ] `LocalFileStore` → `./data/files/<user_id>/`
- [ ] Wire via DI in `app.py`

### 2.3 File upload + linking endpoints (`api/routes/files/`)
- [ ] `POST /api/files/upload` — save file (`workspace_id = NULL` by default)
- [ ] `GET /api/files/` — list user's files
- [ ] `DELETE /api/files/{file_id}` — delete + cascade chunks
- [ ] `POST /api/files/{file_id}/link/thread/{thread_id}`
- [ ] `POST /api/files/{file_id}/link/project/{project_id}`

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

- [ ] `POST /api/projects/` — create
- [ ] `GET /api/projects/` — list
- [ ] `PUT /api/projects/{project_id}` — update title
- [ ] `DELETE /api/projects/{project_id}` — delete (cascades to threads)
- [ ] `POST /api/projects/{project_id}/threads/{thread_id}` — assign thread
- [ ] Frontend: project sidebar, thread grouping

---

## Phase 4 — Workspace scope (embedding retrieval)

The only level where RAG applies. Triggered only when a file is promoted to the shared knowledge base.

### 4.1 Vector storage abstraction
- [ ] Add nullable `workspace_id` to `FileMetadata` (migration)
- [ ] `VectorRepository` protocol: `search_similar_chunks(embedding, k, workspace_id, session)`
- [ ] `PgVectorRepository` (pgvector `<=>`)
- [ ] `SqliteVecRepository` (sqlite-vec virtual table)
- [ ] Select by `DB_ENGINE`

### 4.2 Ingestion + embedding
- [ ] `api/pipelines/ingest.py`: chunk text (configurable size/overlap); formats: text, PDF (`pypdf`), markdown, images (multimodal text extraction)
- [ ] `api/pipelines/embed.py`: `embed_chunks(chunks) -> list[list[float]]` via the embedding `llama-server`; batched
- [ ] Store `ChunkVector` rows; `ON DELETE CASCADE`; re-upload = delete + re-ingest

### 4.3 Promotion + search
- [ ] `POST /api/files/{file_id}/promote-to-workspace` — set `workspace_id`, trigger ingestion + embedding
- [ ] `search_workspace` wired through `VectorRepository`
- [ ] Available as a tool on the plan path (and optionally L1)

---

## Phase 5 — L2: the orchestrator (Plan-and-Execute)

Build only after L0/L1 are solid. **Not** ReAct — finite plan, no open loop.

### 5.1 Engine core
- [ ] `OrchestratorState` (JSON-serializable): run_id, plan, step outputs, status, history
- [ ] `Step`: id, tool, input (may hold `$stepN.field` refs), status, output
- [ ] `engine.py`: sequential step execution; engine resolves `$stepN` refs before each call
- [ ] `planner.py`: full context → finite list of steps (runs on `SYNTHESIS` role, falls back to `PRIMARY`)
- [ ] `synthesizer.py`: full context + step results → answer (runs on `SYNTHESIS` role)
- [ ] Worker steps run on `PRIMARY`; only planner/synthesizer use the reasoning role
- [ ] Verify: at most one capped re-plan on failure (never a loop)

### 5.2 Tool registry
- [ ] `ToolManifest`: name, description, input/output schema, handler, `requires_approval`
- [ ] Load from `configs/tools/*.yaml`; validate I/O against schemas
- [ ] Built-in tools (few, high-level): `fetch_file`, `list_project_files`, `search_workspace`
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

### 6.3 Desktop packaging
- [ ] PyInstaller spec: `api/`, `scripts/`, `shared/`, `dist/`, `configs/`
- [ ] First-run: download both binaries + Qwen3.5-9B (~5.5GB) + Qwen3-Embedding-0.6B → start servers → open browser
- [ ] Test on a clean Windows machine without Python

### 6.4 Frontend completeness
- [ ] File management UI (upload, list, attach, promote to workspace)
- [ ] Project sidebar
- [ ] Agent progress stepper with approval dialog
- [ ] Settings: inference/embedding URLs, model names, `ALLOW_FILE_SUMMARIZATION`, router mode

### 6.5 Observability
- [ ] Structured request logging (request id, user id, duration)
- [ ] `/api/metrics`: token usage, active threads, model status, compaction count

---

## What is intentionally out of scope

- Tauri/Electron wrapper (browser on localhost is enough)
- Mobile clients
- Telegram bot (commented-out code — remove or leave commented)
- Cloud provider support (the OpenAI-compatible URL covers all local cases)
- Multi-tenancy / RBAC (one workspace per deployment; `user_id` FK isolation suffices)
- Real-time collaboration (SSE is one-way and sufficient)
- Incremental chunk diffing on file update (re-ingest whole file)
- Separate vector database (pgvector + sqlite-vec; no Qdrant/Weaviate)
- ReAct / open-ended agent loops (finite plan only)
- Branching/DAG plans, parallel sub-agents (linear, sequential — one llama-server)
- Widget engine / dashboard (Future Work in the thesis text; its "processor" survives as a read-only tool)
