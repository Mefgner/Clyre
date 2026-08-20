# Clyre

Locally-hosted, LLM-powered web app for small teams and households. Runs entirely
on local hardware: no cloud LLM APIs, no external vector DB. Privacy-first local
execution.

- Backend: FastAPI + SQLAlchemy (async) + Alembic
- Frontend: Vue 3 + Vuetify 3 + Pinia + TypeScript
- Inference: llama.cpp (`llama-server`), OpenAI-compatible `/v1/chat/completions`
- DB: SQLite + sqlite-vec (desktop default) or PostgreSQL 16 + pgvector (Docker)
- Orchestration: deterministic plan-and-execute (see `PLAN.md`)

---

## Prerequisites

- Python 3.11+ and [Poetry](https://python-poetry.org/)
- Node.js 20+ and npm
- Enough VRAM for the default chat model (Qwen3.5-9B, ~9B params Q4_K_M)

## First run (source install)

1. Install backend dependencies:

   ```bash
   poetry install
   ```

2. Install and build the frontend:

   ```bash
   npm ci
   npm run build
   ```

   `npm run build` produces `dist/`, which the API serves on the same origin
   (SPA fallback to `index.html`).

3. Create your local environment file from the template and fill in the required
   secrets (`HASHING_SECRET`, `ACCESS_TOKEN_SECRET`):

   ```bash
   cp configs/base.env.example .env
   ```

   `.env` is user-managed and never committed. Generate fresh random secrets
   (>= 32 bytes) yourself.

4. Boot the desktop app. The launcher downloads the pinned llama.cpp binaries and
   the default models on first run, then starts the chat + embedding
   `llama-server` processes and the API:

   ```bash
   poetry run python run-desktop.py
   ```

5. Open http://localhost:6750 in a browser, register, and chat.

### Development (frontend hot reload)

Run the Vite dev server (proxies `/api` to `localhost:6750`):

```bash
npm run dev
```

Frontend: http://localhost:3000

## Docker Compose (team server)

Requires Docker with the NVIDIA Container Toolkit for GPU inference, plus
`HASHING_SECRET` and `ACCESS_TOKEN_SECRET` exported (or in `.env`):

```bash
cp configs/base.env.example .env   # fill in secrets
docker compose up
```

- `db` — PostgreSQL 16 + pgvector
- `llama` / `embedding` — llama.cpp servers (HF model auto-download, `/health`-gated)
- `api` — FastAPI monolith serving both the API and the built frontend

Open http://localhost:6750.

## Development commands

| Task            | Command                         |
| --------------- | ------------------------------- |
| Backend tests   | `poetry run pytest`             |
| Lint            | `poetry run ruff check .`       |
| Frontend check  | `npm run type-check`            |
| Frontend build  | `npm run build`                 |
| Migrations      | `poetry run alembic upgrade head` |
| New migration   | `poetry run alembic revision --autogenerate -m "<msg>"` |

## Configuration

Environment variables are documented in `configs/base.env.example` and defined in
`shared/pyutils/env.py`. Model and binary catalogs live in `configs/models.yaml`
and `configs/binaries.yaml`.

## Roadmap & architecture

See `PLAN.md` for the phased roadmap and `docs/adr/` for architecture decision
records.
