# Operations Runbook

## Table of Contents
1. [Local Prototype](#local-prototype)
2. [Starting and Stopping](#starting-and-stopping)
3. [Database Backup and Restore](#database-backup-and-restore)
4. [Secret Rotation](#secret-rotation)
5. [Rollback Procedure](#rollback-procedure)
6. [Scaling](#scaling)
7. [Monitoring](#monitoring)

---

## Local Prototype

The approved synthetic local demo uses its own procedure and isolated database targets. See the [local demo runbook](local-demo-runbook.md) for the current ports, startup steps, persistence rehearsal, and feature evidence. Do not use these steps for production.

The local runbook is the source of truth for demo readiness. Its matrix distinguishes source review from tests and runtime rehearsal; only owner-captured evidence can move a pending item to passed.

---

## Starting and Stopping

```bash
# Start full stack (production)
docker compose -f docker-compose.prod.yml up -d

# Stop gracefully
docker compose -f docker-compose.prod.yml down

# View logs
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f celery

# Health check
curl http://localhost:8000/health
```

---

## Database Backup and Restore

### Backup

```bash
# Full database backup (plain SQL)
docker exec safebot-db-1 pg_dump \
  -U postgres safebot \
  > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup (preferred for large DBs)
docker exec safebot-db-1 pg_dump \
  -U postgres -Fc safebot \
  > backup_$(date +%Y%m%d_%H%M%S).dump
```

### Restore

```bash
# From plain SQL backup
docker exec -i safebot-db-1 psql -U postgres safebot < backup_20240101_120000.sql

# From compressed backup
docker exec -i safebot-db-1 pg_restore \
  -U postgres -d safebot --clean \
  < backup_20240101_120000.dump
```

### Automated Backups

Consider scheduling a cron job or using a managed database with automated backups. Example cron for daily backups with 7-day retention:

```bash
# /etc/cron.d/safebot-backup
0 2 * * * root docker exec safebot-db-1 pg_dump -U postgres -Fc safebot > /backups/safebot_$(date +\%Y\%m\%d).dump && find /backups -name "safebot_*.dump" -mtime +7 -delete
```

---

## Secret Rotation

### JWT Secret Key

Rotating the JWT secret invalidates all active access tokens immediately. Users will need to log in again.

```bash
# 1. Generate new secret
python -c "import secrets; print(secrets.token_hex(32))"

# 2. Update the secret in your .env or secrets manager
JWT_SECRET_KEY=<new-secret>

# 3. Restart the backend (rolling restart if multiple replicas)
docker compose -f docker-compose.prod.yml restart backend
```

### Database Password

```bash
# 1. Connect to PostgreSQL
docker exec -it safebot-db-1 psql -U postgres

# 2. Change password
ALTER USER postgres WITH PASSWORD 'new-strong-password';

# 3. Update DATABASE_URL in .env
DATABASE_URL=postgresql+asyncpg://postgres:new-strong-password@db:5432/safebot

# 4. Restart backend
docker compose -f docker-compose.prod.yml restart backend celery
```

### Algorand Mnemonic

```bash
# 1. Generate a new Algorand account (requires algokit or algosdk)
python -c "from algosdk import account; pk, addr = account.generate_account(); from algosdk.mnemonic import from_private_key; print(from_private_key(pk))"

# 2. Fund the new account on Algorand mainnet

# 3. Update ALGORAND_MNEMONIC in .env

# 4. Restart celery worker (Algorand writes happen in Celery tasks)
docker compose -f docker-compose.prod.yml restart celery
```

### API Key Compromise (Tenant's API Key)

If a tenant's API key is compromised, the tenant or an admin can rotate it via:

```bash
# Via the API (requires tenant JWT)
curl -X POST https://your-domain/api/v1/auth/regenerate-key \
  -H "Authorization: Bearer <jwt_token>"
```

The old key is immediately invalidated. The new key is returned once and never stored in plaintext.

---

## Rollback Procedure

### Application Rollback (Docker)

```bash
# 1. Identify the previous image tag
docker images | grep safebot

# 2. Update docker-compose.prod.yml to the previous image tag

# 3. Pull and restart
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --no-deps backend celery
```

### Database Migration Rollback (Alembic)

```bash
# Check current migration state
cd backend && alembic current

# Downgrade one step
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade <revision_id>

# List migration history
alembic history --verbose
```

**Note:** Some migrations are not safely reversible (e.g., those that drop columns with data). Always test downgrade scripts in a staging environment. Check `backend/alembic/versions/` for `downgrade()` implementations before running.

---

## Scaling

### Horizontal Scaling

The backend is stateless (session data in Redis, audit data in PostgreSQL). You can run multiple backend replicas behind a load balancer.

```bash
# Scale backend to 3 replicas (Docker Swarm / Compose v3)
docker compose -f docker-compose.prod.yml up -d --scale backend=3
```

Ensure your load balancer sends health checks to `/health/live` (lightweight) for liveness and `/health` (deep check) for readiness.

### Gunicorn Workers

Workers are auto-calculated as `CPU * 2 + 1`. On larger VMs, this scales automatically. Workers recycle after 1000 requests (`max_requests=1000`) to prevent memory accumulation.

### ML Model Memory

With `preload_app = True`, ML models are loaded once in the Gunicorn master process and shared across workers via OS copy-on-write. This saves ~500 MB–1 GB per worker vs. loading models independently.

---

## Monitoring

### Prometheus Metrics

Metrics are exposed at `GET /metrics` (excluded from public API schema). Scrape with Prometheus:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: safebot
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

### Log Aggregation

All structured JSON logs are written to stdout. Collect with:

- **Docker**: `docker compose logs` or configure the `fluentd`/`loki` logging driver
- **Cloud**: Forward container stdout to CloudWatch, Stackdriver, or Datadog

### Sentry Error Tracking

Set `SENTRY_DSN` in `.env` to enable automatic error reporting for both the backend (Python SDK) and optionally the frontend (`@sentry/react`).

### Key Metrics to Watch

| Metric | Alert Threshold | What It Means |
|--------|----------------|---------------|
| `http_requests_total{status="5xx"}` | > 1% of requests | Application errors |
| `http_request_duration_seconds{p99}` | > 2s | Slow responses |
| PostgreSQL connection pool | > 80% utilised | Scale up or tune pool |
| Redis memory | > 80% `maxmemory` | Session data at risk |
| Celery task queue depth | > 1000 | Worker falling behind |
