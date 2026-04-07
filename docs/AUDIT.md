# Production-Readiness Audit: Complete Findings

> Generated 2026-03-26. Implement phases in order. Phases 1–3 are production blockers.

---

## Phase 1: Security Blockers (Must fix before any real users)

### 1.1 — JWT Blocklist Fails Open When Redis Is Down
**File:** `backend/app/dependencies.py:92-107` | **Severity:** CRITICAL

The JWT blocklist check catches `Exception` and logs a warning. If Redis goes down, revoked tokens (from logout) are silently accepted — logged-out users can still access the API.

**Fix:** Fail closed — return 503 when Redis is unreachable, or add a local in-memory blocklist cache as fallback.

---

### 1.2 — Overly Broad Exception Handling in Logout
**File:** `backend/app/api/v1/auth.py:260` | **Severity:** CRITICAL

`except (JWTError, Exception):` swallows all errors including Redis failures, meaning JWT blocklist entries may never be written during logout.

**Fix:** Narrow to `except (JWTError, ValueError):`.

---

### 1.3 — Open Redirect via `redirect_uri`
**File:** `frontend/src/pages/Login/LoginPage.tsx:13-16` | **Severity:** HIGH

`startsWith("/")` validation is bypassable with `//evil.com`. Attacker crafts `?redirect_uri=%2F%2Fevil.com` → user redirected to phishing site after login.

**Fix:** Validate against an explicit allowlist of internal paths, or ensure the path starts with `/` but not `//`.

---

### 1.4 — `setattr()` Mass Assignment on Policy Config
**File:** `backend/app/api/v1/policies.py:68-69` | **Severity:** HIGH

Dynamic `setattr()` applies all Pydantic-validated fields to the ORM model. If a model field is added without a matching schema exclusion, it becomes settable by the client.

**Fix:** Use explicit field assignment instead of looping over `model_dump()`.

---

### 1.5 — Missing Rate Limit on `/reset-password`
**File:** `backend/app/api/v1/auth.py:346` | **Severity:** HIGH

`/forgot-password` has `@limiter.limit("5/minute")` but `/reset-password` has none. An attacker with a leaked token can brute-force passwords.

**Fix:** Add `@limiter.limit("5/minute")` to the reset-password endpoint.

---

### 1.6 — API Key Partially Logged on Auth Failure
**File:** `backend/app/dependencies.py:156` | **Severity:** HIGH

Failed API key lookups log the first 8 and last 4 characters. Repeated probing builds a partial key enumeration attack surface.

**Fix:** Log only a hash or the first 4 characters. Rate-limit auth failure logging by IP.

---

### 1.7 — No Email Format Validation
**File:** `backend/app/schemas/auth.py:16,32,77` | **Severity:** MEDIUM

Email fields use `min_length=3` but no format check. Strings like `"a@b"` are accepted.

**Fix:** Use Pydantic's `EmailStr` type.

---

### 1.8 — API Key Exposed in CI Artifacts
**File:** `.github/workflows/nightly-quality.yml:168-184` | **Severity:** HIGH

Nightly perf test writes an API key to `perf_api_key.txt` then uploads it as a GitHub Actions artifact.

**Fix:** Don't persist the key to a file, or exclude it from artifact upload.

---

## Phase 2: Data Integrity & Resilience
### 2.1 — Initial Migration Downgrade Drops All Tables
**File:** `backend/alembic/versions/0000_initial_schema.py:155-162` | **Severity:** CRITICAL

Running `alembic downgrade -1` on production deletes every table. No safeguard, no confirmation.

**Fix:** Raise an error in the downgrade function with an environment check, or make it a no-op with a clear comment.

---

### 2.2 — Audit Log Background Task Has No Retry
**File:** `backend/app/api/v1/hooks.py:194-205` | **Severity:** HIGH

`_insert_validate_audit_log` runs as a FastAPI background task. If it fails (DB timeout, connection error), the audit entry is silently lost. Compliance trail is incomplete.

**Fix:** Use Celery with retry logic for audit writes, or implement a dead-letter fallback.

---

### 2.3 — Algorand Mock Transactions Return Fake TX IDs Silently
**File:** `backend/app/services/algorand_writer.py:42-46` | **Severity:** MEDIUM

When `algorand_app_id == 0`, a `mock_tx_` ID is returned. Nothing distinguishes these from real on-chain writes. Compliance may think logs are immutable when they're not.

**Fix:** Block `app_id=0` in production via startup validation. Log an explicit warning.

---

### 2.4 — Pagination Offset Has No Upper Bound
**File:** `backend/app/api/v1/audit.py:20` | **Severity:** HIGH

`offset: int = Query(0, ge=0)` with no maximum. An attacker can request `offset=999999999`, forcing an expensive full-table scan.

**Fix:** Add `le=10000` or implement cursor-based pagination.

---

### 2.5 — Frontend Pagination Off-by-One
**File:** `frontend/src/services/auditService.ts:30` | **Severity:** MEDIUM

If the last page returns exactly `page_size` items, the code adds `+ 1` to total, showing a "Next" button that leads to an empty page.

**Fix:** Backend should return a `total` count in the response; frontend should use it.

---

## Phase 3: Production Configuration

### 3.1 — Hardcoded Localhost in CORS & Frontend URL
**File:** `backend/app/config.py:56,60` | **Severity:** CRITICAL

```python
frontend_url: str = "http://localhost:5173"
cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
```

If env vars aren't set, password reset emails contain localhost links and CORS blocks real users.

**Fix:** Add a startup validator that rejects `localhost` origins when `environment == "production"`.

---

### 3.2 — CORS Allows All Methods and Headers
**File:** `backend/app/main.py:66-67` | **Severity:** HIGH

`allow_methods=["*"]` and `allow_headers=["*"]` is overly permissive.

**Fix:** Restrict to `["GET", "POST", "PUT", "DELETE", "OPTIONS"]` and specific headers (`Authorization`, `Content-Type`, `X-API-Key`).

---

### 3.3 — No HTTPS Enforcement
**Files:** `frontend/Dockerfile`, `backend/app/main.py:77-80` | **Severity:** HIGH

Frontend Nginx listens on port 80 only. HSTS header is set but there's no HTTP→HTTPS redirect and no TLS termination config.

**Fix:** Add HTTPS redirect in Nginx, configure TLS certificates, or document the reverse proxy requirement explicitly.

---

### 3.4 — No CSP or Security Headers on Frontend
**File:** `frontend/Dockerfile:24-42` | **Severity:** HIGH

Nginx config has no `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, or `X-XSS-Protection` headers.

**Fix:** Add security headers to the Nginx config block.

---

### 3.5 — DEBUG=true in Default .env
**File:** `backend/.env:23` | **Severity:** MEDIUM

Debug mode enabled by default. If copied to production, SQL queries are logged and stack traces exposed.

**Fix:** Add startup validation: `if environment != "development" and debug: raise RuntimeError(...)`.

---

### 3.6 — Frontend Dockerfile Build ARG Defaults to Localhost
**File:** `frontend/Dockerfile:12` | **Severity:** MEDIUM

`VITE_API_BASE_URL` defaults to `http://localhost:8000/api/v1`. If build arg isn't supplied in production, the frontend hits localhost.

**Fix:** Make the build arg required (no default), or fail the build if not set.

---

### 3.7 — Production Docker Compose Missing Resource Limits
**File:** `docker-compose.prod.yml` | **Severity:** HIGH

No CPU/memory limits on any service. A runaway process can starve everything else.

**Fix:** Add `deploy.resources.limits` for all services.

---

## Phase 4: Frontend Robustness

### 4.1 — No Error Boundary
**File:** `frontend/src/App.tsx` | **Severity:** MEDIUM

No React error boundary. If any component throws, the entire app white-screens with no recovery.

**Fix:** Add a root-level `ErrorBoundary` component wrapping the route tree.

---

### 4.2 — Memory Leak in Dashboard Visibility Listener
**File:** `frontend/src/pages/Dashboard/DashboardPage.tsx:135-143` | **Severity:** MEDIUM

The `visibilitychange` listener can fire after unmount, triggering state updates on an unmounted component.

**Fix:** Verify `removeEventListener` is called in the useEffect cleanup function.

---

### 4.3 — Activity Table Link Button Has No onClick
**File:** `frontend/src/components/shared/ActivityTable.tsx:128-134` | **Severity:** MEDIUM

The link icon button renders as a clickable element but has no `onClick` handler — it does nothing when clicked.

**Fix:** Wire it to a detail view or remove until the functionality is implemented.

---

### 4.4 — SecurityPostureCard Has No Loading Guard
**File:** `frontend/src/pages/Settings/components/SecurityPostureCard.tsx` | **Severity:** MEDIUM

Card is fully interactive during page hydration. Users can toggle settings before data loads.

**Fix:** Accept `isLoading` prop and disable controls while loading.

---

### 4.5 — No Request Retry for Transient Failures
**File:** `frontend/src/services/apiClient.ts` | **Severity:** MEDIUM

Only 401 triggers a retry (token refresh). Network errors and 5xx responses fail immediately with no retry.

**Fix:** Add retry with exponential backoff for 5xx and network errors (1–2 retries max).

---

### 4.6 — Generic Error Messages
**Files:** Multiple pages | **Severity:** LOW

Most API errors show `"Could not X"` without context. Users cannot distinguish network errors from permission errors.

**Fix:** Parse error responses and surface contextual messages.

---

## Phase 5: Observability & Monitoring

### 5.1 — Prometheus Dependency Unused
**File:** `backend/pyproject.toml:26` | **Severity:** MEDIUM

`prometheus-fastapi-instrumentator` is installed but never imported or initialized in `main.py`.

**Fix:** Wire it into `main.py` to expose `/metrics`, or remove the dependency.

---

### 5.2 — Health Check Doesn't Verify ML Models
**File:** `backend/app/api/v1/health.py` | **Severity:** MEDIUM

Health endpoint checks DB and Redis but not whether guardrail models loaded. Server can report healthy but fail all validation requests.

**Fix:** Add model readiness checks to the health response.

---

### 5.3 — No Celery Worker Health Check
**File:** `docker-compose.prod.yml:72-87` | **Severity:** MEDIUM

Celery worker has no healthcheck. If it dies, Algorand audit writes queue up silently.

**Fix:** Add `celery inspect ping` healthcheck.

---

### 5.4 — Sentry Has No Fallback Warning
**File:** `backend/app/main.py:18-25` | **Severity:** MEDIUM

If `SENTRY_DSN` is empty, error tracking is silently disabled with no startup warning.

**Fix:** Log a startup warning when Sentry is not configured in non-development environments.

---

### 5.5 — No Structured Logging Config for Production
**File:** Backend | **Severity:** MEDIUM

structlog is used but no output format, rotation, or sensitive field redaction configured for production.

**Fix:** Configure JSON output, log level filtering, and PII field masking.

---

## Phase 6: CI/CD & Dependencies

### 6.1 — pip-audit Runs as Non-Blocking
**File:** `.github/workflows/ci-pr.yml:74` | **Severity:** HIGH

Security scan uses `|| true` so vulnerability detection never fails the build.

**Fix:** Remove `|| true`. Let it fail the pipeline.

---

### 6.2 — No Python Lock File
**File:** `backend/` | **Severity:** HIGH

Only `pyproject.toml` with `>=` ranges. No lock file. Every CI run and production install may resolve different dependency versions.

**Fix:** Add `pip-compile` output (`requirements.lock`) or switch to Poetry with `poetry.lock`.

---

### 6.3 — No Frontend npm audit in CI
**File:** `.github/workflows/ci-pr.yml` | **Severity:** MEDIUM

Backend has pip-audit; frontend has no equivalent.

**Fix:** Add `npm audit --audit-level=moderate` to the frontend CI job.

---

### 6.4 — CI Secrets Hardcoded in Workflow YAML
**File:** `.github/workflows/ci-pr.yml:37-47` | **Severity:** MEDIUM

`JWT_SECRET_KEY: ci-secret-key` is inline. If the repo ever goes public, it's exposed.

**Fix:** Move to GitHub Secrets (`${{ secrets.CI_JWT_SECRET }}`).

---

### 6.5 — No Deployment Documentation
**File:** Repository root | **Severity:** HIGH

No `DEPLOYMENT.md`, no runbook, no rollback procedure documented anywhere.

**Fix:** Document pre-flight checks, migration strategy, rollback steps, and which dashboards to watch after deploying.

---

## Issue Summary

| Phase | Issues | Critical | High | Medium | Low |
|-------|--------|----------|------|--------|-----|
| 1: Security Blockers | 8 | 2 | 5 | 1 | 0 |
| 2: Data Integrity | 5 | 1 | 2 | 2 | 0 |
| 3: Production Config | 7 | 1 | 4 | 2 | 0 |
| 4: Frontend Robustness | 6 | 0 | 0 | 4 | 2 |
| 5: Observability | 5 | 0 | 0 | 5 | 0 |
| 6: CI/CD & Deps | 5 | 0 | 3 | 2 | 0 |
| **Total** | **36** | **4** | **14** | **16** | **2** |

---

## Implementation Status

- [x] Phase 1: Security Blockers
- [x] Phase 2: Data Integrity & Resilience
- [x] Phase 3: Production Configuration
- [x] Phase 4: Frontend Robustness
- [x] Phase 5: Observability & Monitoring
- [x] Phase 6: CI/CD & Dependencies
