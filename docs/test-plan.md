> **Local demo status:** This file is a historical production-hardening plan, not a record of tests run for the October 2026 local prototype. Use the [local demo runbook and feature matrix](local-demo-runbook.md) for current scope, owner-captured results, and remaining acceptance checks. Do not treat this historical checklist as current test evidence.

 Plan: Production-Readiness Hardening                                                               
                                                                                                    
 Context                                                                                            
                                                                                                    
 Before deploying Safebot to production, a deep audit of the backend, frontend, and infrastructure   identified several gaps against industry best practices. Many audit items were already addressed    (structured logging, pool_pre_ping, Redis persistence, Nginx security headers, health checks,       resource limits, Celery health checks). This plan covers the remaining genuine issues, prioritized 
  by production impact.

 Triage: Already Fixed (No Action Needed)

 - DB composite index on audit_logs(tenant_id, created_at) — exists in migration
 - pool_pre_ping=True — already in database.py:25
 - Structured logging with PII masking — already in main.py:20-58
 - Deep health check (DB + Redis + ML models) — already in health.py:14-43
 - Redis persistence volume — already in docker-compose.prod.yml
 - Celery healthcheck — already in docker-compose.prod.yml
 - Docker resource limits — already in docker-compose.prod.yml
 - Nginx security headers + CSP — already in frontend Dockerfile
 - Celery exponential backoff — already in worker.py:64,90
 - Input size limits (8000 chars) — already in Pydantic schemas
 - Sentry integration — already in main.py:62-75

 ---
 Phase 1: Critical — Security & Stability (Effort: S each)

 1A: Celery Worker Connection Pool Leak

 File: backend/app/worker.py
 Problem: _update_audit_tx_id (line 99) and _update_policy_tx_id (line 113) each call
 create_engine() on every invocation, never disposing. Under load, this exhausts PostgreSQL
 max_connections.
 Fix: Create a module-level lazy _sync_engine singleton. Register a worker_shutdown signal to call  
 _sync_engine.dispose().

 1B: Gunicorn Worker Recycling + Preload

 File: backend/gunicorn.conf.py
 Problem: No max_requests (memory leaks accumulate forever). No preload_app (each of ~9 workers     
 loads 3 ML models independently, ~4-8 GB wasted RAM).
 Fix: Add:
 max_requests = 1000
 max_requests_jitter = 100
 preload_app = True

 1C: Policy Engine SQL Safety

 Files: backend/app/services/guardrails/policy_engine.py, backend/app/config.py
 Problem: top_k parameter passed directly to SQL LIMIT with no upper bound — a client can pass      
 top_k=999999 for DoS. Similarity threshold hardcoded.
 Fix: Add policy_max_top_k: int = 20 and policy_similarity_threshold: float = 0.65 to config. Clamp 
  top_k = min(top_k, settings.policy_max_top_k) at start of check_message.

 1D: Algorand Network Production Validation

 Files: backend/app/main.py (lifespan), backend/app/config.py
 Problem: algorand_network defaults to "testnet". If deployed with a real algorand_app_id but       
 forgetting to switch network, blockchain writes go to testnet.
 Fix: In lifespan, when ENVIRONMENT=production and algorand_app_id != 0, validate algorand_network  
 == "mainnet".

 ---
 Phase 2: High — Security Gaps (Effort: S-M)

 2A: Rate Limit on API Key Rotation (S)

 File: backend/app/api/v1/auth.py
 Problem: POST /auth/regenerate-key has no rate limit. Stolen JWT → rapid key rotation DoS.
 Fix: Add @limiter.limit("3/hour") decorator + request: Request parameter.

 2B: Audit Log Retention Task (M)

 Files: backend/app/worker.py, backend/app/config.py
 Problem: safety_configs.log_retention_days exists (default 30) but nothing enforces it. Table      
 grows unbounded.
 Fix: Add a Celery Beat periodic task (daily) that deletes audit_logs older than log_retention_days 
  per tenant, in batches of 1000 rows.

 2C: Graceful Shutdown Resource Cleanup (S)

 File: backend/app/main.py (lifespan shutdown)
 Problem: Lifespan shutdown only logs — doesn't close DB engine or Redis pool.
 Fix: Add await engine.dispose() and Redis client close in the shutdown block.

 ---
 Phase 3: Frontend Performance (Effort: S each)

 3A: React Code Splitting

 File: frontend/src/App.tsx
 Problem: All 10 page components eagerly imported. Entire app bundled in initial load.
 Fix: Replace static imports with React.lazy() + <Suspense> wrapper:
 const DashboardPage = React.lazy(() => import('./pages/Dashboard/DashboardPage'))
 // ... same for all authenticated routes

 3B: ErrorBoundary Production Reporting

 File: frontend/src/components/shared/ErrorBoundary.tsx
 Problem: Errors only logged to console in dev. Production crashes are invisible.
 Fix: Add Sentry.captureException(error) in componentDidCatch (Sentry SDK already on backend, add   
 @sentry/react to frontend). Fallback: POST to a backend error endpoint.

 ---
 Phase 4: Observability (Effort: M)

 4A: Request ID Tracing

 File: backend/app/main.py (new middleware)
 Problem: No correlation ID across request lifecycle — production debugging requires timestamp      
 guessing.
 Fix: Add middleware that generates UUID4 request_id (or reads X-Request-ID header), binds to       
 structlog context via structlog.contextvars.bind_contextvars(), returns as response header. All    
 existing log calls automatically include it.

 ---
 Phase 5: CI/CD Hardening (Effort: S each)

 5A: CI Secret Masking

 File: .github/workflows/ci-pr.yml
 Fix: Add ::add-mask:: for API keys in test output. Verify pytest --tb=short doesn't leak keys in   
 tracebacks.

 5B: Database Migration Locking

 File: backend/alembic/env.py
 Problem: Concurrent deploys can corrupt migration state.
 Fix: Acquire PostgreSQL advisory lock before running migrations: SELECT pg_advisory_lock(123456).  

 ---
 Phase 6: Documentation (Effort: S-M)

 6A: SECURITY.md

 Document known limitations and their mitigations:
 - localStorage token storage (mitigated by CSP + 15min JWT expiry, httpOnly cookies planned        
 post-MVP)
 - CSRF not needed while using Authorization header (constraint on future cookie adoption)
 - API key timing side-channel (mitigated by SHA-256 cache key design)

 6B: Operations Runbook (docs/operations.md)

 - Backup/restore procedures (pg_dump/pg_restore)
 - Secret rotation procedures (JWT key, DB creds, Algorand mnemonic)
 - Rollback procedure (Alembic downgrade, Docker image rollback)

 ---
 Critical Files

 - backend/app/worker.py — Celery connection leak fix
 - backend/gunicorn.conf.py — max_requests + preload_app
 - backend/app/services/guardrails/policy_engine.py — top_k cap
 - backend/app/config.py — new settings
 - backend/app/main.py — Algorand validation, request ID middleware, graceful shutdown
 - backend/app/api/v1/auth.py — rate limit on key rotation
 - frontend/src/App.tsx — code splitting
 - frontend/src/components/shared/ErrorBoundary.tsx — error reporting
 - backend/alembic/env.py — migration locking
 - .github/workflows/ci-pr.yml — secret masking

 Verification

 1. cd backend && pytest -v — all existing tests still pass
 2. cd frontend && npx vitest run — all frontend tests pass
 3. cd frontend && npm run build — build succeeds with code splitting
 4. Manual: start with make dev, verify /health returns healthy
 5. Manual: check gunicorn config loads correctly with gunicorn --check-config -c gunicorn.conf.py  
 app.main:app
