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

## Layout
Per domain: `api/routes/<domain>/views.py` (endpoints) → `services/<domain>.py` (logic) → `crud/<domain>.py` (queries) → `schemas/<domain>.py` (DTOs) → `models/<domain>.py` (ORM).
- `api/pipelines/`: inference, summarize, embed, ingest, fs/
- `api/services/retrieval.py`: `fetch_file` / `list_project_files` / `search_project` — plain async funcs shared by chat and orchestrator
- `api/modules/orchestrator/`: plan-and-execute engine

## Conventions
- Logic in services, queries in crud, `commit()` in services only. `get_db_session` from `api/db.py`.
- Auth: `Bearer` access token + refresh token as httponly cookie.
- NDJSON (chat) vs SSE (orchestrator) — don't conflate.
- Black (line length 96) + Ruff.

## Dev
- Backend: `poetry run python run-desktop.py`
- Frontend: `npm run dev` / `npm run type-check`
- Migrations: run by launchers before the API starts — `run-desktop.py` and the Dockerfile CMD (`python -m db_migrations`); CLI: `poetry run alembic upgrade head`, new revision: `poetry run alembic revision --autogenerate -m "<msg>"`, verify: `poetry run alembic check`
- Env: copy `configs/base.env` → `.env`
- Deployment: runtime-agnostic monolith — desktop script (`run-desktop.py`, SQLite default) or `docker compose up` (PostgreSQL + pgvector); `DB_ENGINE`/`DATABASE_URL` select the backend.

## Status
See `PLAN.md` for the full phased roadmap and what is done vs pending.

## Known weaknesses
Frontend issues triage (from an outside review, with severity + suggested fix order): `web/FRONTEND_ISSUES.md`. Check it before touching frontend code.
