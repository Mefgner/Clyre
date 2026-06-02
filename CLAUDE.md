# Clyre — Agent Instructions

## What this project is

**Clyre** is a bachelor thesis project: a locally-hosted LLM-powered web application for small teams and households. It is a **modular monolith** (FastAPI backend + Vue 3 frontend) that runs entirely on local hardware — no cloud LLM APIs, no external vector databases.

The thesis evaluates: local LLM deployment, context management strategies, and agent-based workflows on consumer hardware. "Constrained hardware" means a consumer GPU ≥8GB VRAM — not a datacenter, not a potato. The USP is privacy-first local execution (GDPR angle), not "runs on anything".

Target user (honest framing for defense): a technically literate person who already owns a consumer GPU (gaming PC / Mac) and has privacy requirements — a family, a 3-person micro-startup, a lab without IT. Not "every household". One machine serves the LAN; everyone on it gets their own accounts, threads, and files.

Academic supervisor expects: clean architecture, repository pattern, DI, Pydantic validation, Alembic migrations.

---

## Hard constraints — never violate these

- **No cloud LLM APIs.** No OpenAI, Anthropic, Gemini as inference providers. The USP is 100% local execution. LiteLLM is acceptable only as a translation layer if needed for format compatibility, never to call cloud inference.
- **No microservices.** Everything stays inside the FastAPI monolith, divided by module folders — not by network boundaries.
- **No ReAct/while-True agent loops.** Execution middle does not reason in a loop. The model reasons only at two points (planner, synthesizer); the middle is a finite sequence of typed tool calls. See Orchestrator.
- **No Tauri/Electron** at this stage. The desktop experience is `python run-desktop.py` → FastAPI serves built Vue as static files + API from one process.
- **No passive RAG injection.** Do not inject top-k chunks into every prompt automatically. Context is managed per scope — see Context Management.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic v2 |
| Frontend | Vue 3, Vuetify 3, Pinia, TypeScript |
| Inference | llama.cpp (`llama-server` binary), OpenAI-compatible `/v1/chat/completions` |
| DB (Docker/teams) | PostgreSQL 16 + pgvector |
| DB (Desktop/household) | SQLite + sqlite-vec (WAL mode) |
| Migrations | Alembic (not yet added — highest priority structural task) |
| Packaging | PyInstaller → single executable for desktop mode |

---

## Model requirements

**Default chat model:** Qwen3.5-9B (Q4_K_M, ~5.5GB VRAM)
- Hybrid architecture (Gated Delta Networks + sparse Attention) → KV cache grows near-linearly → 262K context fits in 8GB VRAM
- Natively multimodal (vision encoder) → images in files work out of the box
- Target hardware: consumer GPU ≥8GB (RTX 3070/3080 class)

**Default embedding model:** Qwen3-Embedding-0.6B
- Multilingual (the deployment context is Slovak / German / Russian / English — an English-only embedder like bge-small is unacceptable)
- `VECTOR_DIM = 1024` (native; Matryoshka allows truncating to 512 if a smaller index is wanted — must match the column dimension)
- Runs as a **second `llama-server` process** on its own port (chat 6760, embed 6761). One `llama-server` instance serves exactly one model.
- VRAM budget on 8GB: 9B-Q4 (~5.5GB) + embedder (~0.7GB) ≈ 6.2GB, leaving room for KV cache.

**Minimum floor:** 9B parameters for the chat model. Models below 9B cannot reliably follow the structured output the orchestrator requires. This is an empirical finding the thesis should demonstrate, not just assert.

**Model tier is a config knob, not a reliability crutch.** Raising the tier (the `SYNTHESIS_*` reasoning role) is correct when the *task* needs more reasoning — planning and answer synthesis. It is the wrong fix when *tool integration is fragile* — fix the tools (make them higher-level, constrain decoding) instead. Tools run on the `PRIMARY` worker model and must stay reliable there; leaning on a 30B to make tool calls work breaks the hardware floor. See Inference provider abstraction for role-based tiering.

**Inference profiles** in `configs/inference.yaml` cover 8GB, 12GB, 16GB, 24GB. The 4GB/6GB profiles are below the model floor — remove or mark "unsupported".

---

## Inference provider abstraction

`OpenAICompatiblePipeline` calls the OpenAI-compatible `/v1/chat/completions` endpoint. Three **model roles**, each a configurable endpoint:

```
PRIMARY_BASE_URL=http://localhost:6760     # chat + worker steps (default 9B)
PRIMARY_MODEL=Qwen3.5-9B
SYNTHESIS_BASE_URL=                          # planner + synthesizer; empty → falls back to PRIMARY
SYNTHESIS_MODEL=                             # optionally a larger LOCAL model for big plans + complex answers
EMBEDDING_BASE_URL=http://localhost:6761     # embedder (second llama-server)
EMBEDDING_MODEL=Qwen3-Embedding-0.6B
```

Any OpenAI-compatible backend works without code changes: llama.cpp, Ollama, LM Studio, vLLM. Do not add provider-specific client libraries or branching logic. The abstraction is the URL. (`LLAMA_*` env names are kept as deprecated aliases.)

**Role-based model tiering.** Reasoning load is asymmetric: the planner and synthesizer see full context and carry the hard reasoning; worker steps are isolated, constrained tool calls. So `SYNTHESIS_*` (the "reasoning tier") may point at a larger model than `PRIMARY_*` (the "worker tier"). Default household config leaves `SYNTHESIS_*` empty → one 9B does everything (8GB cannot hold 9B + a big model at once). A user with more VRAM or a second LAN node opts into a bigger reasoning model via config alone. **The synthesis model must remain LOCAL** — it sees the user's full context; routing that to a cloud API breaks the hard constraint and the privacy USP, even though it is "only planning".

**Multimodal content:** the pipeline must support `content` as a list of content blocks, not just a string:
```python
content = [
    {"type": "text", "text": "..."},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
]
```
llama.cpp handles this natively when a multimodal model is loaded.

**Constrained decoding:** tool calls and structured node outputs use llama.cpp grammar / `response_format` (JSON schema) so the model's output is valid by construction. This removes parse/repair logic. Note: constraints guarantee *syntax* (parseable), not *semantics* (right choice) — semantic reliability comes from few high-level tools + the verify step.

The class lives in `api/pipelines/inference.py`.

---

## Deployment modes

### Desktop (household, primary thesis demo)
- Small trusted group (family), one machine serves the LAN, `python run-desktop.py`
- SQLite (`aiosqlite`, WAL mode) + sqlite-vec for vectors
- Two llama.cpp subprocesses (chat + embed) launched by `scripts/llama_launcher.py`
- FastAPI serves built Vue from `dist/` as static files
- Multi-user: accounts/JWT still apply (each family member has own threads/files)
- Target: package as `.exe`/`.msi` via PyInstaller

### Docker (teams, secondary mode)
- Multi-user, `docker-compose up`
- PostgreSQL + pgvector
- llama.cpp as separate container(s) (`ghcr.io/ggml-org/llama.cpp:server-cuda`)
- nginx reverse-proxies frontend + API

Do not over-engineer the Docker mode. It is a secondary demonstration.

---

## Architecture: module layout

```
api/
  routes/<domain>/views.py     — FastAPI endpoints only, no logic
  services/<domain>.py         — Business logic, orchestrates CRUD + pipelines
    services/retrieval.py      — fetch_file / list_project_files / search_workspace
                                 (plain async functions; called by BOTH chat and orchestrator)
    services/router.py         — fast-vs-plan classifier
  crud/<domain>.py             — SQLAlchemy queries, no business logic
  schemas/<domain>.py          — Pydantic DTOs
  models/<domain>.py           — SQLAlchemy ORM models
  pipelines/
    inference.py               — OpenAI-compatible LLM client (multimodal)
    summarize.py               — Summarization (chat compaction + file overflow)
    embed.py                   — Embedding client (second llama-server, workspace only)
    ingest.py                  — File ingestion + chunking (workspace files only)
    fs/                        — File system abstraction for uploads
  modules/
    orchestrator/              — Plan-and-Execute engine
      engine.py                — worker loop, step execution, ref resolution
      state.py                 — OrchestratorState (JSON-serializable)
      planner.py               — produces N-step plan (full context)
      synthesizer.py           — produces final answer (full context + results)
      registry.py              — tool registry (native + MCP)
      yaml_parser.py           — agent/tool manifest → Pydantic
configs/
  agents/*.yaml                — Agent manifests
  tools/*.yaml                 — Tool manifests
  models.yaml                  — LLM model registry
  binaries.yaml                — llama.cpp binary registry
  inference.yaml               — Per-VRAM inference parameters
shared/pyutils/                — Shared utilities (env, logs)
scripts/                       — Startup scripts (downloader, llama_launcher)
web/                           — Vue 3 frontend
```

Adding a new domain: pair `routes/<domain>/views.py` + `services/<domain>.py` + `schemas/<domain>.py` + `crud/<domain>.py`. Register the router in `routes/views.py`.

---

## Response pipeline

Every chat message flows through one branch point. The branch is the only "agent vs not" decision.

```
POST /api/chat  { message, attached_file_ids?, mode? }

mode: auto → router (one constrained classify call) decides fast | plan
      or forced fast / plan

── FAST ───────────────────────────────────────────────
  • build context: thread history (compacted if over limit)
    + explicitly attached files (injected at a STABLE position)
  • generate answer
      └─ if model requests a read-only tool: execute → feed result
         back → continue generating.   (rung 1: +1 round-trip)
  • stream (NDJSON); save assistant message in a FRESH session

── PLAN ───────────────────────────────────────────────
  • create agent_run(pending) → enqueue → return run_id
  • in-process worker (RAM = source of truth):
      Planner   (full context)            → N-step plan
      for each step: call tool (typed in/out; may hide a sub-machine;
                     read-only runs silently, write → approval gate)
      Synthesizer (full context + results) → answer
  • checkpoint to DB only at: approval, completion
  • live progress via in-memory pub/sub → SSE
```

### Layering (build bottom-up — do not build it all at once)
- **L0** — fast chat: history → answer. (Already works.)
- **L1** — fast chat + a single read-only inline tool call ("ask about my file"). Covers ~80% of use.
- **L2** — plan path: planner / steps / synthesizer.
- **L2+** — approval gate (only once write tools exist); checkpoint persistence (only for plan path).
- **Cross-cutting** — context compaction (when history overflows); workspace embedding search (only when a shared KB exists); the auto-router itself (MVP can ship a manual "agent mode" toggle and add auto-classification later).

L0 + L1 are the spine. Everything else is a branch attached when a concrete need appears; none of it is load-bearing for a working assistant.

---

## Context management strategy

Context is managed per scope. **No passive RAG injection.** Passive top-k injection leaves knowledge gaps (top-k misses relevant chunks), especially damaging on small local models. The thesis demonstrates this empirically.

The retrieval functions (`fetch_file`, `list_project_files`, `search_workspace`) live in `api/services/retrieval.py` as **plain async functions**. The fast path calls them directly; the orchestrator calls them through the tool registry. The registry is a manifest wrapper, not where the logic lives — no duplication.

**Prefill rule:** injected context (files, retrieved chunks) goes in a **stable position** (system prompt at the front, or appended at the end), never spliced into the middle of history. Mid-insertion invalidates the KV cache from that point on and forces re-prefill of the suffix.

### Chat scope — full context, compaction on overflow
Thread-attached files are included **whole**. No chunking, no embeddings.
When thread history exceeds the window: `summarize()` the oldest portion (rolling compaction), keep recent messages verbatim, emit `context_compacted` so the user is told.
If a single attached file does not fit:
- `ALLOW_FILE_SUMMARIZATION=true` (default): summarize the file before injection.
- `ALLOW_FILE_SUMMARIZATION=false`: fall back to on-the-fly chunk+embed+retrieve, and tell the user retrieval mode is active. This flag selects a *strategy* (lossy summary vs precise-but-gappy retrieval); it must never silently truncate.

### Project scope — tool-driven fetch
Project files are accessed via tools, not injected. `list_project_files(project_id)`, `fetch_file(file_id)`. No embeddings. If a fetched file overflows, apply chat-scope overflow logic.

### Workspace scope — embedding retrieval (the only level where RAG applies)
The workspace corpus is too large to enumerate. `search_workspace(query, workspace_id, k)` → top-k chunks.

Vector search is the only thing that differs between SQLite and Postgres. Abstract it behind `VectorRepository`:
```python
async def search_similar_chunks(
    embedding: list[float],
    k: int,
    workspace_id: str,
    session: AsyncSession,
) -> list[ChunkResult]: ...
```
Two implementations selected by `DB_ENGINE`: `PgVectorRepository` (pgvector `<=>`), `SqliteVecRepository` (sqlite-vec virtual table). No other code knows the difference. (A single-field `RAGScope` wrapper is not worth it — pass `workspace_id` directly.)

### File scope model
`FileMetadata.workspace_id` is **nullable**. A file is embedded **only when explicitly promoted to the workspace knowledge base** (its `workspace_id` is set). Chat/project files keep `workspace_id = NULL` and are never embedded. On deletion, chunks cascade (`ON DELETE CASCADE`). File modification = delete all chunks + re-ingest (no diff).

### Summarization component (`api/pipelines/summarize.py`)
Single `summarize(text, target_tokens) -> str`. Used by chat compaction and file overflow. Token counting via llama.cpp `/tokenize`.

---

## Orchestrator — Plan-and-Execute

Lives in `api/modules/orchestrator/`. **Not** LangGraph, **not** ReAct. The planner emits a finite list of steps up front; the worker executes them; the synthesizer writes the answer. Reliability is a property of the engine, not the model.

### What a step is
A step is **one tool call** — nothing else.
```
Step: id, tool, input (typed), status, output (typed | None)
```
Three rules that keep it honest:
1. **A step is always a tool call. No bare "think" steps.** The model reasons only in the planner and synthesizer. Mid-plan reasoning is packaged *as a tool* (a high-level tool may hide a deterministic sub-machine — "garbage → structured content").
2. **Output → input wiring is resolved by the engine, not the model.** A step's input may reference a prior step (`"$step1.output.file_id"`); the engine substitutes before the call. Dynamic data flow without a re-planning loop.
3. **Plans are linear.** No branching/DAG, no parallelism (a single `llama-server` serializes anyway — "sub-agents" are *logical* context isolation executed sequentially). Verify failure → at most one capped re-plan, never a loop.

### Context policy per unit
- **Planner / synthesizer** — full context (compacted history + goal / + step results). Run on the `SYNTHESIS` reasoning role (falls back to `PRIMARY`).
- **Worker steps** — isolated, minimal context (just what the step needs). Run on the `PRIMARY` worker model. Shorter prefill → faster and more reliable on a 9B.

### Tools
- `ToolManifest`: `name`, `description`, `input_schema`, `output_schema`, `handler`, `requires_approval: bool`. Loaded from `configs/tools/*.yaml`.
- Keep tools **few and high-level**. Fewer tools → easier selection; simpler schemas + constrained decoding → nothing to parse.
- A tool `handler` may be a pure function, a deterministic state machine, or a sub-agent — opaque to the caller. **Hidden sub-machines must be read-only.** Any write stays a top-level tool so its approval is visible; approval must never be swallowed inside an encapsulated tool.

### Persistent runs — checkpoint model
RAM is the source of truth for a live run; the DB stores **full-state checkpoints** only at boundaries.

- **One table, `agent_run`**: `id`, `user_id`, `agent`, `input`, `status` (pending|running|waiting_approval|done|failed|interrupted), `state_snapshot` (JSON — full `OrchestratorState`), `result`, `error`, timestamps. There is **no** per-event table.
- Checkpoints written at: creation (`pending`), approval (`waiting_approval` + full snapshot), terminal (`done`/`failed`).
- `OrchestratorState` **must be JSON-serializable** — the snapshot is the resume unit. The terminal snapshot's `history` doubles as the audit trail.
- Live SSE streams from an **in-memory pub/sub** keyed by `run_id`. No DB polling.
- **Reload/reconnect:** run live in RAM → reconnect to the live stream (history before reload is not replayed); run only in DB → show last checkpoint (coarse status, or approval dialog); `running` row with no RAM entry → mark `interrupted` on startup.
- **A `running` task is lost on server restart** (its state was never checkpointed). Accepted cost for household scale — the user re-triggers. Only `waiting_approval` runs are resumable.

### Human-in-the-loop for writes
Approval gates the **Execute step's write tool call (pre-write)**, not Verify — you approve *before* the side effect.
1. Worker hits a tool with `requires_approval: true` → writes `approval_required` event to the live stream, checkpoints `waiting_approval` + full snapshot, suspends (awaits an `asyncio.Event` keyed by `run_id`).
2. `POST /api/agent/{run_id}/approve` | `/reject` sets the event → worker resumes.
3. Reject → `error` event, status `failed`, worker moves on.
This defines the trust boundary between the agent and external state.

### MCP as tool source
MCP servers register additional tools into the same `ToolRegistry` at startup. The orchestrator does not distinguish native from MCP. MCP write tools must be `requires_approval: true`.

### Frontend
Progress stepper (Queued → Planning → Executing → Done) driven by SSE events, not raw chain-of-thought. Approval dialog triggered by `approval_required`.

---

## What is not yet implemented (thesis gaps)

- **Alembic migrations** — currently `create_all` on startup. Replace before any schema change.
- **Router** (`api/services/router.py`)
- **Retrieval functions** (`api/services/retrieval.py`)
- **Summarization** (`api/pipelines/summarize.py`)
- **Embedding client** (`api/pipelines/embed.py` empty) + second `llama-server` wiring
- **Ingestion** (`api/pipelines/ingest.py` empty)
- **File system abstraction** (`api/pipelines/fs/` empty)
- **File upload/management endpoints** — models exist, routes do not
- **Project management endpoints** — model exists, routes do not
- **Workspace scope** — `workspace_id` not yet on `FileMetadata`
- **Orchestrator** (`api/modules/orchestrator/` does not exist)
- **Tool registry + MCP** — not started
- **Token revocation** — logout only deletes the cookie
- **`wait_for_startup` timeout** — infinite loop, no max retries

---

## Conventions

- New endpoints: Pydantic schemas in `schemas/`, logic in `services/`, queries in `crud/`.
- `session.commit()` in the service layer, never in CRUD.
- `get_db_session` dependency from `api/db.py` for all endpoints.
- Auth: `Authorization: Bearer <access_token>` header; `refresh_token` httponly cookie. Extract via `utils/web.py`.
- **Chat streaming uses NDJSON** (`application/x-ndjson`), each line a `StreamingBlock`. **Orchestrator progress uses SSE** (`text/event-stream`). These are two different transports — do not conflate them.
- No comments that explain what code does. Comments only for non-obvious constraints or workarounds.
- Black formatter, line length 96. Ruff linter. Run before committing.

---

## Dev workflow

```bash
# Backend (starts both llama-server processes + uvicorn)
poetry run python run-desktop.py

# Frontend (separate terminal)
npm run dev

# Type-check frontend
npm run type-check
```

Environment: copy `configs/base.env` to `.env`, fill in secrets (`HASHING_SECRET`, `ACCESS_TOKEN_SECRET`, `REFRESH_TOKEN_SECRET`).
