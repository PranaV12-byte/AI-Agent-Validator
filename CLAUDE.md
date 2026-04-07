# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Safebot** — an AI Guardrails Middleware MVP for SMBs. A multi-tenant platform that validates, sanitizes, and audits AI agent interactions using ML-based guardrails (prompt injection detection, PII redaction, semantic policy matching) with optional Algorand blockchain audit immutability.

## Common Commands

All top-level shortcuts are in the `Makefile`:

```bash
make db        # Start PostgreSQL (pgvector:pg16, port 55432) and Redis via Docker
make migrate   # Run alembic migrations (cd backend && alembic upgrade head)
make dev       # Start backend (uvicorn, port 8000, hot-reload)
make frontend  # Start frontend dev server (port 5173)
make test      # Run backend tests (cd backend && pytest -v)
make celery    # Start Celery worker for Algorand async tasks
```

### Backend
```bash
cd backend && pytest -v                          # All tests
cd backend && pytest tests/test_hooks.py -v      # Single test file
cd backend && pytest -k "test_name" -v           # Single test by name
cd backend && alembic revision --autogenerate -m "description"  # New migration
```

### Frontend
```bash
cd frontend && npm run dev          # Dev server
cd frontend && npm run build        # Production build
cd frontend && npx vitest run       # Unit tests (one-shot)
cd frontend && npm run test:watch   # Unit tests (watch)
cd frontend && npm run e2e          # Playwright E2E (headless)
cd frontend && npm run e2e:headed   # Playwright E2E (headed)
```

## Architecture

### Backend (`backend/app/`)

**Entry point:** `main.py` — registers all routers, warms ML models on startup, configures CORS and rate limiting.

**Request flow for SDK validation:**
1. Request hits `api/v1/hooks.py` (authenticated via API key — `X-API-Key` header)
2. `dependencies.py` resolves tenant from API key (bcrypt + TTL cache)
3. `services/guardrails/` runs ML checks: injection detection → PII redaction → policy engine
4. Audit log written; violations optionally queued to Celery → Algorand via `services/algorand_writer.py`

**Key layers:**
- `api/v1/` — FastAPI routers (auth, hooks, policies, audit, dashboard, health)
- `services/guardrails/` — ML models: `injection_detector.py`, `pii_redactor.py`, `policy_engine.py`
- `services/` — business logic (auth, policy, audit, algorand, perf_trace, api_key_cache)
- `models/` — SQLAlchemy ORM (Tenant, Policy, PolicyEmbedding, AuditLog, ApiUsage, SafetyConfig)
- `worker.py` — Celery tasks for async Algorand blockchain writes
- `core/rate_limit.py` — SlowAPI bucketed by API key or IP

**Database:** PostgreSQL 16 + pgvector extension. Async SQLAlchemy engine (pool size 10, max overflow 20). Migrations in `backend/alembic/versions/`.

**Config:** `app/config.py` (Pydantic BaseSettings). Copy `.env.example` to `backend/.env` to get started.

### Frontend (`frontend/src/`)

React 19 + TypeScript + Vite. State management via React Context (Auth, Theme). HTTP via Axios (`services/apiClient.ts`).

**Routing:** React Router v7. Top-level providers in `main.tsx`: `AuthProvider` → `ThemeProvider`.

**Page structure:** `pages/` contains page components; `components/` for shared UI; `services/` for API calls matching backend endpoints.

**Testing:** Vitest (jsdom) for unit tests; Playwright (Chromium, sequential) for E2E under `e2e/`. MSW used for mocking in unit tests.

### CI/CD (`.github/workflows/`)

- **`ci-pr.yml`** — Runs on every PR: backend pytest + frontend vitest/build + 9 stable Playwright E2E specs (rate-limit E2E excluded as non-blocking).
- **`nightly-quality.yml`** — Full suite at 02:00 UTC: all 11 E2E specs + perf smoke test (`backend/scripts/load_validate_smoke.py`, 200 req / 10 concurrency). Perf is non-blocking (`continue-on-error`).

### Infrastructure

Dev stack via `docker-compose.dev.yml`:
- PostgreSQL on host port **55432** (not 5432)
- Redis on port **6379**

Production uses `gunicorn.conf.py` with `UvicornWorker`, workers = `(CPU * 2) + 1`.
