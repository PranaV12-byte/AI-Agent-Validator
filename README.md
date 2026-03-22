# Safebot — AI Guardrails for SMBs

> AI Guardrails Middleware MVP for AlgoBharat Hack Series 3.0

## Quick Start (Dev)

```bash
# 1. Start infrastructure
make db

# 2. Copy and configure env
cp .env.example backend/.env

# 3. Run migrations
make migrate

# 4. Start backend
make dev

# 5. Start frontend (Phase 7+)
make frontend
```

## Tech Stack
- **Backend:** FastAPI + SQLAlchemy (async) + pgvector + Celery
- **Frontend:** React + Vite
- **DB:** PostgreSQL 16 + pgvector extension
- **Cache/Queue:** Redis 7
- **Blockchain:** Algorand (testnet)

## Architecture
See `MVP_Blueprint_Part1.md` for full schema and phase plan.

## CI Gates (Phase F)

- PR gate (`.github/workflows/ci-pr.yml`)
  - backend: `python -m pytest -q`
  - frontend: `vitest` + `npm run build`
  - stable Playwright E2E suite (rate-limit test excluded)
- Nightly gate (`.github/workflows/nightly-quality.yml`)
  - full backend/frontend test suites
  - full Playwright suite
  - non-blocking extras:
    - deferred rate-limit E2E (`frontend/e2e/rate-limit.spec.ts`)
    - perf smoke script (`backend/scripts/load_validate_smoke.py`)

### Temporary Performance Note

Performance SLO hardening is intentionally deferred. Functional and security gates are blocking; performance and deferred E2E checks are non-blocking in nightly runs until optimization is completed.
