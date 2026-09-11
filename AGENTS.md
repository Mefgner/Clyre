# Clyre — Project Orientation

Locally-hosted, LLM-powered web app for small teams and households (bachelor thesis). Modular monolith — FastAPI + Vue 3 — running entirely on local hardware: no cloud LLM APIs, no external vector DB. USP: privacy-first local execution.

## Design preferences
- Deterministic orchestration: code decides the workflow, the LLM only does the reasoning. Keep the model's decision surface small — few, high-level tools, no open-ended loops.
- Selective context management: explicit context injection + structured scopes (user facts, project memory, chat memory); semantic RAG is one mechanism among several, used only where it pays off — not a global layer.
- LLM reasons only at the edges: planner + synthesizer; the steps between are a finite, sequential plan (Plan-and-Execute), never ReAct.
- Runtime owns existence, LLM owns cognition: tools/plugins detect events and do deterministic work; the model is woken only when cognition is needed.
- Local-first and monolithic: no cloud LLM APIs — inference goes through the OpenAI-compatible layer only; one FastAPI monolith, no microservices. Runtime-agnostic: same code, two delivery shapes — desktop via `python run-desktop.py` (no Tauri/Electron), team server via `docker compose up`.
- OpenCode is a benchmark baseline (agentic control), not the foundation.

## Stack
- Backend: Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic v2; Alembic migrations
- Frontend: Vue 3, Vuetify 3, Pinia, TypeScript
- Inference: llama.cpp (`llama-server`) behind the OpenAI-compatible layer only — never vendor SDKs
- DB: SQLite + sqlite-vec WAL (desktop default); PostgreSQL 16 + pgvector for teams. `DB_ENGINE`/`DATABASE_URL` construct the SQLAlchemy engine; the vector repository is selected from the live engine dialect.
- Models: one chat model, Qwen3.5-9B (Q4_K_M), performs every cognitive role; the production floor is 9B params. Qwen3-Embedding-0.6B provides embeddings with `VECTOR_DIM = 1024`. Configure the two endpoints with `CHAT_*` and `EMBEDDING_*`. Roles such as router, parser, planner, and synthesizer are call profiles on the chat model, not separate model tiers.

## Layout
Per domain: `api/routes/<domain>/views.py` (endpoints) → `services/<domain>.py` (logic) → `crud/<domain>.py` (queries) → `schemas/<domain>.py` (DTOs) → `models/<domain>.py` (ORM).
- `api/pipelines/`: inference, embed, ingest, fs/
- `api/services/context_window.py`: shared exact-token chat-history selector for chat, retry, and future router
- `api/services/retrieval.py`: `fetch_file` / `list_project_files` / `search_project` — plain async funcs shared by chat and orchestrator
- `api/modules/orchestrator/`: plan-and-execute engine (planned, not yet created)
- Frontend under `web/`: `components/` (auto-imported), `pages/`, `stores/` (Pinia), `repos/` (API clients per domain), `entities/`, `plugins/`, `router/`, `utils/`

## Response pipeline
`POST /api/chat/stream` is the single chat entry point; there is no public mode field
- **FAST (router):** today every message goes directly to chat. M5 adds one constrained chat-model classification (the shared token-aware history suffix + registry names) inside the same path → plain chat or a registered capability pipeline (`parse → execute → synthesize`). The model never sees raw tools. Streams **NDJSON**.
- **PLAN** *(deferred, post-thesis)*: planner → sequential tool steps → synthesizer. Checkpointed at approval/completion. Progress via **SSE**.

Design details: `docs/plans/tool-contract.md`, rationale: ADR-draft 11 (`docs/adr/drafts/11-deterministic-routing.md`).

## Context management
- No passive RAG. Chat scope = selected whole files + a token-aware suffix of complete recent `user + assistant` turns; project scope = tool-driven fetch; per-project index = embedding retrieval (the only RAG level, behind `VectorRepository`; no global index).
- Full chat history stays in storage/UI. The model-facing window is selected per request; messages are never truncated, turns are never split, and history is never summarized automatically.
- The mandatory prompt is system + selected files + current request + output reserve. Candidate history boundaries are measured from the real `/apply-template` prompt and `/tokenize` count against `/props`; persisted token counts are advisory only.
- Injected context goes at a stable position, never mid-history. Normal chat, retry, and the future router use the same selector.

## Orchestrator
Plan-and-Execute, not ReAct. A step = one tool call. Engine resolves `$stepN` refs; linear plans; verify failure → at most one capped re-plan. Write tools require approval (human-in-the-loop). Worker steps use isolated context; planner/synthesizer use full context. All roles share the chat model.

## Conventions
- Logic in services, queries in crud, `commit()` in services only. `get_db_session` from `api/db.py`.
- Auth: `Bearer` access token + refresh token as httponly cookie.
- NDJSON (chat) vs SSE (orchestrator) — don't conflate.
- Black (line length 96) + Ruff.
- ADR publication: keep working notes, source material, and unapproved alternatives in `docs/adr/local/`; it is intentionally local and ignored by Git. Publish a record under `docs/adr/drafts/` only after explicit owner approval, with a self-contained rationale, alternatives, and consequences; do not include private working material. Start publishable records from `docs/adr/template.md`. Local implementation tasks belong in `PLAN.md`/`PLAN-NOTE`; confirmed defects belong in `docs/known-issues.md`.
- In-code plan notes (executable backlog): when working on a plan or build and you find an inconsistency, bug, or missing piece that does not belong in `PLAN*.md`, record it in the code instead of losing it:
  - Problem/required fix at an existing entity → a one-line comment directly above it: `# PLAN-NOTE(<plan-id>): <short description>`.
  - Needed function/class that does not exist yet → declare it with a full signature, no logic: body = docstring (arbitrary length; may describe intent, neighbors, and callers) + `raise NotImplementedError`. Mark the declaration line with `# STUB(<plan-id>)`.
  - Stubs must never be called from working code paths — they fail loudly by design.
  - Closing rule: implementing the fix or stub removes its marker in the same change; never leave orphaned markers.

## Dev
- Backend: `poetry run python run-desktop.py`
- Frontend: `npm run dev` / `npm run type-check`
- Verification: backend — `poetry run ruff check .`, `poetry run black --check .`, `poetry run pytest` (unit-only: `-m "not e2e"`; the `e2e` marker needs live PostgreSQL/llama-server). Frontend — `npm run type-check`.
- Pre-commit: backend + frontend hooks (eslint `--fix`, vue-tsc, ruff/black/pyright/pytest unit-only); needs Node/npm with `npm install` once. For large or cross-cutting commits always run the full sweep first: `poetry run pre-commit run --all-files`.
- Migrations: run by launchers before the API starts — `run-desktop.py` and the Dockerfile CMD (`python -m db_migrations`); CLI: `poetry run alembic upgrade head`, new revision: `poetry run alembic revision --autogenerate -m "<msg>"`, verify: `poetry run alembic check`
- Env: copy `configs/base.env.example` → `.env`
- Deployment: runtime-agnostic monolith — desktop script (`run-desktop.py`, SQLite default) or `docker compose up` (PostgreSQL + pgvector); `DB_ENGINE`/`DATABASE_URL` configure the database engine, and dialect-specific behavior follows the live engine.

## Known issues
`docs/known-issues.md` lists reviewed weaknesses outside the planned-rework scope, including the affected-file list. If you edit any file mentioned there, read that document first and account for the noted problem: fix it if it falls within your change's scope, or at minimum avoid regressing it.

## Status
See `PLAN.md` for the full phased roadmap and what is done vs pending.
