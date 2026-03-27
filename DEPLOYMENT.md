# Deployment Runbook

> Safebot production deployment guide. Follow every section in order.

---

## Pre-flight Checklist

Before deploying, verify all of the following:

- [ ] All CI checks green on the release commit
- [ ] `DEPLOYMENT.md` changes reviewed for this release
- [ ] `.env.prod` updated with required secrets (see Required Environment Variables below)
- [ ] `ALGORAND_APP_ID` is set to a real app ID (not `0`)
- [ ] `SENTRY_DSN` is set and pointing to the correct project
- [ ] `CORS_ORIGINS` contains only real production domains (no `localhost`)
- [ ] `FRONTEND_URL` is set to the real production domain
- [ ] `JWT_SECRET_KEY` is a random 32+ character secret (`python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `DEBUG=false`
- [ ] Database backup completed and verified restorable
- [ ] Notify team of upcoming deployment window

---

## Required Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis connection string (`redis://...`) |
| `JWT_SECRET_KEY` | Random secret ≥ 32 chars |
| `CORS_ORIGINS` | JSON array of allowed origins, e.g. `["https://app.example.com"]` |
| `FRONTEND_URL` | Production frontend URL for password reset emails |
| `POSTGRES_USER` | PostgreSQL user |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_DB` | PostgreSQL database name |
| `VITE_API_BASE_URL` | Backend API base URL for frontend build |

Optional but strongly recommended:

| Variable | Description |
|---|---|
| `ALGORAND_APP_ID` | Algorand smart contract app ID (required for real audit trails) |
| `ALGORAND_MNEMONIC` | Algorand wallet mnemonic |
| `SENTRY_DSN` | Sentry error tracking DSN |

---

## Migration Strategy

**Always run migrations before deploying new application code.**

```bash
# 1. Connect to the backend container (or run locally against prod DB)
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# 2. Verify migration applied
docker compose -f docker-compose.prod.yml exec backend alembic current
```

**Rules:**
- Never run `alembic downgrade` on production — the initial migration guard will block it, but do not attempt it.
- For destructive schema changes, take a DB snapshot first.
- Test migrations against a copy of the production DB before deploying.

---

## Deployment Steps

```bash
# 1. Pull latest images / build
docker compose -f docker-compose.prod.yml build --no-cache

# 2. Run database migrations (before bringing up new app code)
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 3. Bring up all services
docker compose -f docker-compose.prod.yml up -d

# 4. Verify health
curl -s https://api.example.com/health | python -m json.tool

# 5. Check logs for startup errors
docker compose -f docker-compose.prod.yml logs backend --tail=50
docker compose -f docker-compose.prod.yml logs celery --tail=50
```

---

## Post-Deployment Verification

Run these checks within 5 minutes of deploying:

```bash
# Health endpoint — all checks must be "ok"
curl -s https://api.example.com/health

# Liveness probe
curl -s https://api.example.com/health/live

# Prometheus metrics reachable (internal only)
curl -s http://localhost:8000/metrics | head -20
```

**Dashboards to watch:**
- Sentry — watch for new error spikes in the first 15 minutes
- Prometheus / Grafana — request rate, latency (p95), error rate
- Celery — queue depth and worker health (`celery inspect ping`)

---

## Rollback Procedure

If a deployment causes errors, roll back immediately:

```bash
# 1. Revert to previous image tag
docker compose -f docker-compose.prod.yml down

# Rebuild from previous commit
git checkout <previous-commit-sha>
docker compose -f docker-compose.prod.yml build

# 2. If migrations were applied, assess carefully before downgrading
#    (downgrade on the initial schema migration is blocked — contact the team)

# 3. Bring previous version up
docker compose -f docker-compose.prod.yml up -d

# 4. Verify health
curl -s https://api.example.com/health
```

**When to rollback immediately:**
- `/health` returns 503 for more than 2 minutes
- Error rate in Sentry spikes > 10× baseline
- Any data corruption detected in audit logs

---

## Scaling Notes

- Backend workers: set by `gunicorn.conf.py` (`(CPU * 2) + 1` workers). Adjust CPU limit in `docker-compose.prod.yml`.
- Celery concurrency: currently `--concurrency=2`. Increase for higher Algorand throughput.
- PostgreSQL connection pool: `DATABASE_POOL_SIZE` (default 10) and `DATABASE_MAX_OVERFLOW` (default 20).
