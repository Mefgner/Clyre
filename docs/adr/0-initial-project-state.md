# Initial project state

This record is a snapshot of where Clyre stands at the start of the architectural
work the following ADRs describe. It is not a decision — it is the baseline every
later ADR builds on or changes. Full target architecture lives in `CLAUDE.md`;
the roadmap in `PLAN.md`.

## Identity

- **Project:** Clyre — locally-hosted, LLM-powered web app for small teams and households.
- **Nature:** bachelor thesis (UKF Nitra, Applied Informatics). Modular monolith.
- **Version:** `0.0.1-3`, "Pre-Alpha-2". License Apache-2.0.
- **USP:** 100% local execution (privacy / GDPR angle). No cloud LLM APIs.

## Runtime environment

- **Language:** Python ≥ 3.11.
- **Dev machine:** Windows 11, PowerShell.
- **Dependency management:** Poetry (`package-mode = false` — run from source, not installed as a package).
- **Two deployment targets:**
  - *Desktop (household):* `python run-desktop.py` — SQLite (`aiosqlite`), llama.cpp launched as a subprocess; the launcher downloads the binary + model on first run (via `pooch`).
  - *Docker (teams):* `docker-compose` — PostgreSQL (`asyncpg`), llama.cpp as a separate container.

## Backend stack (present in `pyproject.toml`)

- **Web:** FastAPI (`>=0.116`), Uvicorn.
- **Validation/config:** Pydantic v2, `pydantic-settings`.
- **ORM:** SQLAlchemy 2.0 async.
- **DB drivers:** `aiosqlite` (desktop) + `asyncpg` (Docker) — selected at runtime.
- **Vectors:** `pgvector` (Postgres side). No sqlite-vec yet.
- **Auth:** `pyjwt` (access + refresh tokens), `argon2-cffi` (password hashing).
- **LLM client:** `httpx` against llama.cpp's OpenAI-compatible endpoint.
- **Config files:** `pyyaml` (models / binaries / inference registries under `configs/`).
- **Misc:** `pooch` (binary/model downloader), `colorlog`.
- **Tooling:** Black + Ruff, line length 96; Pylint. `telegram-bot`, `web`, `public`, `configs` excluded from formatting/linting.

## Frontend stack

- Vue 3 + Vuetify 3 + Pinia + TypeScript, under `web/`. Built output served by FastAPI as static files in desktop mode.

## What already works

- **Auth:** local registration/login, JWT access header + refresh httponly cookie.
- **Chat (L0):** message → thread history → llama.cpp → streamed answer (NDJSON). This is the working spine.
- **ORM models:** user, thread, message, file, project (with relationships — some buggy, see below).
- **Inference:** a single `llama-server` (chat model only) reachable over the OpenAI-compatible API.
- **Startup:** schema created via `create_all` (no migrations yet).

## What is skeleton / empty

- Embedding, ingestion, file-system, and tool pipelines are empty files.
- No file-upload, project-management, or agent endpoints (some models exist without routes).
- No orchestrator, no tool registry, no second (embedding) `llama-server`.
- No Alembic, no token revocation, no `wait_for_startup` timeout.

## Known baseline bugs

Five confirmed bugs carried into this work (data-corrupting or crash-level) — see
the "Known bugs" section of `CLAUDE.md` and Phase 0 of `PLAN.md`. They are fixed
before any new feature work.

## Inherited cruft

- A `telegram-bot/` directory (commented-out / excluded) from an earlier idea — out of scope, left untouched for now.
