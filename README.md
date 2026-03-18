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
