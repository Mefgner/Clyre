# Runtime-agnostic monolith with hybrid delivery (Docker + desktop script)

## Context

Two deployment targets with conflicting needs: households want a zero-friction
single binary; teams want reproducible server setup with a real database. Supporting
both naively duplicated DB drivers, vector backends, and startup logic — and a
script-only answer forced teams to hand-install PostgreSQL, which is worse than Docker.

## Decision

Keep the app a runtime-agnostic monolith configured entirely by env (`DATABASE_URL`,
`SMALL_*` / `BIG_*` / `EMBEDDING_*` model URLs). SQLAlchemy + Alembic are backend-agnostic; the
only DB-specific code lives behind `VectorRepository` (pgvector vs sqlite-vec). Then ship
two thin delivery shapes over the same code:

- **Desktop (solo/household):** `run-desktop.py` / PyInstaller exe — SQLite + sqlite-vec
  (default), llama-server launched as a native subprocess (direct GPU, no container-driver pain).
- **Team server:** `docker compose up` — `db` (PostgreSQL + pgvector) + `clyre`
  (FastAPI monolith + Vue static). llama-server runs natively on the host for direct GPU
  (the container reaches it via `host.docker.internal`), or as a compose service where
  nvidia-container-toolkit is set up.

## Alternatives considered

| Option | Why tempting | Why rejected |
|---|---|---|
| Docker-only (llama.cpp in containers too) | One uniform runtime | GPU pass-through breaks on Windows/WSL2; desktop install becomes heavy |
| Script-only, no Docker | Simplest single path | Teams expect `compose up`; PostgreSQL without Docker is a manual install |
| Two separate apps (desktop vs server) | Isolation | Doubles the codebase for a thesis |

## Consequences

**Positive:** one codebase, one startup story, direct GPU in both shapes; Docker only where
it actually earns its keep (PostgreSQL + reproducible server).
**Negative:** two packaging artifacts to maintain (PyInstaller spec + compose file); the
llama-server host path (`host.docker.internal`) is a small documented quirk.
**Follow-ups:** compose `db` + `clyre` services; a systemd/Windows-service wrapper for the
desktop script as an optional headless team mode without Docker.

## Thesis link

"Analyzing deployment possibilities in a local environment" — a hybrid strategy, not a
forced either/or; feeds the analysis chapter.
