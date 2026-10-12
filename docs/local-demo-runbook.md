# SafeBot Local Demo Runbook

Updated: 2026-10-13  
Target rehearsal deadline: 2026-10-14 13:00 IST

This runbook covers the approved local prototype using synthetic tenants and requests. It is not a production deployment guide. The demo has no hosting, paid fallback, live chain writes, model downloads, or new dependency installation in scope.

## Current local profile

| Service | Local address | Target |
| --- | --- | --- |
| Web UI | `http://127.0.0.1:5176` | Frontend dev server |
| API | `http://127.0.0.1:8102` | Backend dev server; health at `/health` |
| PostgreSQL | `localhost:55434` | Separate `sb_backend_demo` and `sb_backend_test` databases |
| Redis | `localhost:16380` | Database `/0` for demo; `/1` for tests |

Use the already provisioned local services and cached dependencies. The repository's default `make db` profile uses different ports and must not be used for this demo. If an expected service is unavailable, stop and have the owner restore the approved local profile; do not reset databases, remove volumes, pull images, or create replacement services.

## Configuration boundaries

The owner has provisioned ignored local environment files at `backend/.env` and `frontend/.env.local`; the startup commands below reuse them. Do not display, copy, or commit their contents. The backend file targets `sb_backend_demo` and Redis database `/0`; guarded tests use `sb_backend_test` and Redis `/1`. Keep backend secrets out of the frontend environment; `frontend/.env.local` should contain only the loopback API URL. Do not place credentials in source files, logs, database rows, or commits.

Keep these demo settings explicit:

```text
ENVIRONMENT=development
GROQ_LIVE_ENABLED=false
GROQ_FREE_PLAN_CONFIRMED=false
GROQ_API_KEY=
ALGORAND_APP_ID=0
ALGORAND_MNEMONIC=
SMTP_HOST=
SENTRY_DSN=
```

The Groq key remains unset until the owner confirms free-tier eligibility and supplies the local key through the approved backend environment. Live provider use requires a separate action-time check. No external Groq provider call was made in the current tests or browser rehearsal. With Algorand app ID `0`, worker tasks should report `skipped`; no transaction ID should be fabricated or linked as a chain record.

## Start, check, and restart the app

Open a PowerShell window and start the backend from the approved worktree. The existing virtual environment and ignored backend settings file are reused; no install or model download is needed.

```powershell
Set-Location 'C:\Dev\Projects\AI Agent Validater\.agent-work\backend-local-demo\backend'
$env:FRONTEND_URL = 'http://127.0.0.1:5176'
$env:CORS_ORIGINS = '["http://127.0.0.1:5176"]'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:DO_NOT_TRACK = '1'
& '..\..\..\backend\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8102
```

In a second PowerShell window, start the UI. Vite also reads the owner's ignored `frontend/.env.local`; the API URL is pinned here to the same loopback host used by CORS.

```powershell
Set-Location 'C:\Dev\Projects\AI Agent Validater\.agent-work\backend-local-demo\frontend'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8102/api/v1'
$env:DO_NOT_TRACK = '1'
npm run dev -- --host 127.0.0.1 --port 5176
```

Check `Invoke-RestMethod http://127.0.0.1:8102/health`, then open `http://127.0.0.1:5176`. Use synthetic accounts and messages only. Stop the two app processes with Ctrl+C when finished.

For an app-process restart, stop each process with Ctrl+C and rerun the same backend and frontend commands in their respective windows. Keep PostgreSQL, Redis, and their volumes running. The backend offline flags prevent Hugging Face/Transformers downloads and disable Hugging Face telemetry for that process; they do not enable or authorize Groq or Algorand calls.

## Persistence rehearsal

1. Create a synthetic tenant, change a protection setting, and submit a synthetic request that creates an audit row.
2. Reload the UI and confirm the account, setting, and audit row remain visible.
3. Stop and restart the backend and frontend processes. Keep the database and Redis containers and their volumes running.
4. Log back in and confirm the same synthetic state remains. Record the exact observation and any failures in the task handoff.

Never use `docker compose down -v`, volume deletion, database drops, or shared Redis flushes during this rehearsal. The test database and Redis `/1` are reserved for the owner's guarded test run.

## Audit and worker feature matrix

Sol's round-two source review accepted the bounded audit repairs. The following test and browser results were captured by the root verification agent on 2026-10-13. The backend tests used synthetic fixtures and mocked worker behavior; they did not submit a real chain transaction. These focused results do not imply that the full repository suites, a cold process restart, or a live Groq call passed.

| Feature | Evidence observed | Still pending |
| --- | --- | --- |
| Backend audit and worker behavior | Focused backend suite: 36 passed in 30.19 seconds, using synthetic fixtures/mocked workers. Coverage includes audit filters, tenant isolation, detail/export sanitization, hash labels, disabled/mock Algorand handling, worker failures, and retention. | Full backend suite remains pending. |
| Audit UI and shared activity display | 25 tests passed across the three listed frontend files. Before chat UI additions, the full frontend suite passed 211 tests across 28 files and the production build passed. | Re-run after the protected-chat UI is added. |
| Browser routes and local model path | One background browser page exercised signup, login, policies, settings, integration, account, and audit routes. Synthetic validation through the cached model produced allow, redact, and block outcomes. The audit view showed no original email after reload, with no page errors. | Cold restart persistence remains pending. |
| CSV export and history integrity | Included in the passing focused backend suite; presentation sanitization is copy-only and preserves stored history/hash values. | Full-suite coverage remains pending. |
| Optional Algorand | Focused backend/UI tests cover mocked worker/UI states. No live transaction was sent; app ID `0` remains disabled. | No live chain transaction or explorer verification is claimed. |
| Live Groq conversation | Deferred; live flag/free-plan confirmation are false and the key remains unset. | Owner confirmation, local key placement if approved, and a separately authorized smoke run. |
| Cold restart persistence | Browser reload of the audit view passed. | Stop/restart API and UI processes while keeping DB/Redis running, then confirm synthetic account/settings/audit state. |

### Focused test files recorded by the root verification agent

```text
backend/tests/test_audit_extended.py
backend/tests/unit/test_audit_presentation.py
backend/tests/unit/test_algorand_worker_safety.py
frontend/src/pages/AuditLog/components/AuditTable.test.tsx
frontend/src/pages/AuditLog/components/AuditDetailDrawer.test.tsx
frontend/src/components/shared/ActivityTable.test.tsx
```

Run the repository's full suites and complete the cold-restart rehearsal before marking the demo ready. Do not change the existing database or Redis targets as part of that verification.
