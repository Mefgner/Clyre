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
- Backend: Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic v2
- Frontend: Vue 3, Vuetify 3, Pinia, TypeScript
- Inference: llama.cpp (`llama-server`), OpenAI-compatible `/v1/chat/completions`
- DB: SQLAlchemy (async) — SQLite + sqlite-vec WAL (desktop default); PostgreSQL 16 + pgvector via the same `DB_ENGINE` switch (Docker Compose for teams)
- Migrations: Alembic

## Models
- Default chat: Qwen3.5-9B (Q4_K_M). Hard floor: 9B params.
- Embedding: Qwen3-Embedding-0.6B, `VECTOR_DIM = 1024`.
- Three tiers (env): `SMALL_*` (chat + worker steps), `BIG_*` (planner + synthesizer; falls back to SMALL — if only one tier is configured, it takes all load), `EMBEDDING_*`. One client class, configured per tier. The BIG tier must stay local (sees full user context).

## Layout
Per domain: `api/routes/<domain>/views.py` (endpoints) → `services/<domain>.py` (logic) → `crud/<domain>.py` (queries) → `schemas/<domain>.py` (DTOs) → `models/<domain>.py` (ORM).
- `api/pipelines/`: inference, summarize, embed, ingest, fs/
- `api/services/retrieval.py`: `fetch_file` / `list_project_files` / `search_project` — plain async funcs shared by chat and orchestrator
- `api/modules/orchestrator/`: plan-and-execute engine

## Response pipeline
`POST /api/chat` (`mode: auto|fast|plan`; `plan` deferred post-thesis):
- **FAST (router):** every message → one constrained SMALL-tier classification (recent history + registry names) → plain chat or a registered capability pipeline (`parse → execute → synthesize`). The model never sees raw tools. Streams **NDJSON**.
- **PLAN** *(deferred, post-thesis)*: planner → sequential tool steps → synthesizer. Checkpointed at approval/completion. Progress via **SSE**.

Design details: `docs/plans/tool-contract.md`, rationale: ADR-draft 11 (`docs/adr/drafts/11-deterministic-routing.md`).

## Context management
- No passive RAG. Chat scope = whole files + compaction on overflow; project scope = tool-driven fetch; per-project index = embedding retrieval (the only RAG level, behind `VectorRepository`; no global index).
- Injected context goes at a stable position, never mid-history.

## Orchestrator
Plan-and-Execute, not ReAct. A step = one tool call. Engine resolves `$stepN` refs; linear plans; verify failure → at most one capped re-plan. Write tools require approval (human-in-the-loop). Worker steps = isolated context on `SMALL`; planner/synthesizer = full context on `BIG`.

## Conventions
- Logic in services, queries in crud, `commit()` in services only. `get_db_session` from `api/db.py`.
- Auth: `Bearer` access token + refresh token as httponly cookie.
- NDJSON (chat) vs SSE (orchestrator) — don't conflate.
- Black (line length 96) + Ruff.

## Dev
- Backend: `poetry run python run-desktop.py`
- Frontend: `npm run dev` / `npm run type-check`
- Pre-commit: backend + frontend hooks (eslint `--fix`, vue-tsc, ruff/black/pyright/pytest unit-only); needs Node/npm with `npm install` once. For large or cross-cutting commits always run the full sweep first: `poetry run pre-commit run --all-files`.
- Migrations: run by launchers before the API starts — `run-desktop.py` and the Dockerfile CMD (`python -m db_migrations`); CLI: `poetry run alembic upgrade head`, new revision: `poetry run alembic revision --autogenerate -m "<msg>"`, verify: `poetry run alembic check`
- Env: copy `configs/base.env` → `.env`
- Deployment: runtime-agnostic monolith — desktop script (`run-desktop.py`, SQLite default) or `docker compose up` (PostgreSQL + pgvector); `DB_ENGINE`/`DATABASE_URL` select the backend.

## Known issues
`docs/known-issues.md` lists reviewed weaknesses outside the planned-rework scope. If you
edit any file mentioned there, read that document first and account for the noted problem:
fix it if it falls within your change's scope, or at minimum avoid regressing it.

Affected files (backend): `api/app.py`, `api/db.py`, `api/utils/timing.py`, `api/services/chatting.py`, `api/services/auth.py`, `api/services/file.py`, `api/routes/files/views.py`, `api/routes/chatting/views.py`, `api/routes/auth/views.py`, `api/utils/web.py`, `api/pipelines/inference.py`, `api/pipelines/embed.py`, `api/pipelines/fs/store.py`, `alembic/env.py`
Frontend: `web/components/chat/PrettyMarkdown.vue`, `web/components/chat/PromptBar.vue`, `web/repos/thread.ts`, `web/stores/thread.ts`, `web/stores/auth.ts`, `web/utils/api.ts`, `web/pages/index.vue`, `web/pages/chat.vue`
Infra/config: `run-desktop.py`, `scripts/llama_launcher.py`, `scripts/build_db_url.py`, `docker-compose.yml`, `pyproject.toml`, `requirements.txt`, `configs/inference.yaml`, `.gitignore`

## Status
See `PLAN.md` for the full phased roadmap and what is done vs pending.
