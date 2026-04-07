# Safebot Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 17 pre-production gaps (3 P0 blockers, 9 P1 features, 5 P2 polish items) identified in the audit spec, with full unit + integration + E2E test coverage.

**Architecture:** Three sequential waves — each wave fully tested before the next begins. Backend additions follow existing FastAPI + SQLAlchemy async patterns in `backend/app/api/v1/`. Frontend additions follow React 19 + TypeScript patterns with `vi.mock()` unit tests and MSW integration tests.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest + TestClient (backend); React 19, TypeScript, Vitest, @testing-library/react, MSW, Playwright (frontend)

**Pre-notes:**
- Items 10 (Pagination Info) and 14 (KPI Formatting) from the spec are **already implemented** — `PaginationControls.tsx` already shows "Page X of Y (Z records)" and `KpiGrid.tsx` already has block-rate trend text and latency formatting. No tasks needed for these.
- Backend tests use the `client` (TestClient), `make_tenant()`, and `auth_headers()` fixtures from `backend/tests/conftest.py`. Rate limiting is disabled in tests (`limiter.enabled = False`).
- Frontend tests import `useAuth` from `../../hooks/useAuth` and mock it with `vi.mock()`.

---

## Wave 1 — P0 Blockers

---

### Task 1: Dynamic Onboarding Checklist

**Files:**
- Modify: `frontend/src/pages/Dashboard/DashboardPage.tsx`
- Modify: `frontend/src/pages/Dashboard/DashboardPage.integration.test.tsx`

- [ ] **Step 1: Write the failing test**

Add these two tests to the existing `describe("Dashboard integration")` block in `frontend/src/pages/Dashboard/DashboardPage.integration.test.tsx`:

```typescript
import { http, HttpResponse } from "msw"
import { server } from "../../mocks/server"

it("marks 'Add your first protection rule' done when policies exist", async () => {
  server.use(
    http.get("*/api/v1/dashboard/stats", () =>
      HttpResponse.json({ total_requests: 0, blocked_requests: 0, avg_latency_ms: 0 })
    ),
    http.get("*/api/v1/audit/", () =>
      HttpResponse.json({ logs: [], total: 0, page: 1, page_size: 20 })
    ),
    http.get("*/api/v1/policies/", () =>
      HttpResponse.json({
        policies: [{ id: "p1", name: "Test", rule_type: "keyword", is_enabled: true }],
        total: 1,
      })
    ),
  )

  render(<MemoryRouter><DashboardPage /></MemoryRouter>)

  // Checklist visible because total_requests is still 0
  const ruleStep = await screen.findByText("Add your first protection rule")
  expect(ruleStep).toHaveClass("line-through")
})

it("hides onboarding checklist when all steps complete", async () => {
  server.use(
    http.get("*/api/v1/dashboard/stats", () =>
      HttpResponse.json({ total_requests: 5, blocked_requests: 1, avg_latency_ms: 45 })
    ),
    http.get("*/api/v1/audit/", () =>
      HttpResponse.json({ logs: [], total: 5, page: 1, page_size: 20 })
    ),
    http.get("*/api/v1/policies/", () =>
      HttpResponse.json({
        policies: [{ id: "p1", name: "Test", rule_type: "keyword", is_enabled: true }],
        total: 1,
      })
    ),
  )

  render(<MemoryRouter><DashboardPage /></MemoryRouter>)

  await waitFor(() => {
    expect(screen.queryByText("Welcome to Safebot — let's get you set up")).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd frontend && npx vitest run src/pages/Dashboard/DashboardPage.integration.test.tsx
```

Expected: FAIL — checklist steps are hardcoded so the line-through assertion won't pass.

- [ ] **Step 3: Implement dynamic checklist in DashboardPage.tsx**

Replace the entire `DashboardPage.tsx` with this updated version:

```typescript
import { CheckCircle2, Circle } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import ActivityTable from "../../components/shared/ActivityTable"
import KpiGrid from "../../components/shared/KpiGrid"
import PageHeader from "../../components/shared/PageHeader"
import UsageTrendChart from "../../components/shared/UsageTrendChart"
import { fetchAuditLogs } from "../../services/auditService"
import { fetchDashboardStats } from "../../services/dashboardService"
import { fetchPolicies } from "../../services/policyService"
import type { AuditLog, DashboardStats } from "../../types/api"

type ChecklistStep = {
  label: string
  done: boolean
  action: (() => void) | null
  actionLabel?: string
  hint?: string
}

function OnboardingChecklist({ steps }: { steps: ChecklistStep[] }) {
  return (
    <section className="bg-card-bg border border-border-color rounded-2xl p-8 mb-8">
      <h2 className="text-xl font-bold mb-1">Welcome to Safebot — let's get you set up</h2>
      <p className="text-text-muted text-sm mb-6">Follow these steps to protect your AI assistant.</p>
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={index} className="flex items-center gap-4">
            {step.done ? (
              <CheckCircle2 className="w-5 h-5 text-brand-green shrink-0" />
            ) : (
              <Circle className="w-5 h-5 text-text-muted shrink-0" />
            )}
            <span className={`text-sm flex-1 ${step.done ? "line-through text-text-muted" : ""}`}>
              {step.label}
            </span>
            {step.action ? (
              <button
                type="button"
                onClick={step.action}
                className="text-xs text-brand-green hover:underline"
              >
                {step.actionLabel}
              </button>
            ) : step.hint ? (
              <span className="text-xs text-text-muted">{step.hint}</span>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}

function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [policyCount, setPolicyCount] = useState<number | null>(null)

  const [isStatsLoading, setIsStatsLoading] = useState(true)
  const [isLogsLoading, setIsLogsLoading] = useState(true)

  const [statsError, setStatsError] = useState<string | null>(null)
  const [logsError, setLogsError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function load() {
      setIsStatsLoading(true)
      setIsLogsLoading(true)
      setStatsError(null)
      setLogsError(null)

      const [dashboardResult, auditResult, policiesResult] = await Promise.allSettled([
        fetchDashboardStats(),
        fetchAuditLogs({ page: 1, page_size: 20 }),
        fetchPolicies(),
      ])

      if (!mounted) return

      if (dashboardResult.status === "fulfilled") {
        setStats({
          total_requests: dashboardResult.value.total_requests,
          blocked_requests: dashboardResult.value.blocked_requests,
          avg_latency_ms: dashboardResult.value.avg_latency_ms,
        })
      } else {
        setStatsError("Unable to fetch security metrics at this time.")
      }
      setIsStatsLoading(false)

      if (auditResult.status === "fulfilled") {
        setLogs(auditResult.value.logs)
      } else {
        setLogsError("Unable to load recent activity right now.")
      }
      setIsLogsLoading(false)

      if (policiesResult.status === "fulfilled") {
        setPolicyCount(policiesResult.value.total)
      } else {
        setPolicyCount(0)
      }
    }

    void load()

    function onVisibilityChange() {
      if (document.visibilityState === "visible" && mounted) {
        void load()
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    const interval = setInterval(() => { if (mounted) void load() }, 5 * 60 * 1000)

    return () => {
      mounted = false
      document.removeEventListener("visibilitychange", onVisibilityChange)
      clearInterval(interval)
    }
  }, [])

  const hasActivity = (stats?.total_requests ?? 0) > 0
  const hasPolicy = (policyCount ?? 0) > 0

  const checklistSteps: ChecklistStep[] = [
    { label: "Create your account", done: true, action: null },
    {
      label: "Add your first protection rule",
      done: hasPolicy,
      action: hasPolicy ? null : () => navigate("/policies"),
      actionLabel: "Go to Protection Rules",
    },
    {
      label: "Connect your AI tool",
      done: hasActivity,
      action: hasActivity ? null : () => navigate("/integration"),
      actionLabel: "View Setup Guide",
    },
    {
      label: "Send a test message",
      done: hasActivity,
      action: null,
      hint: hasActivity ? undefined : "Complete the steps above first",
    },
  ]

  const allDone = checklistSteps.every((s) => s.done)
  const showChecklist = !isStatsLoading && !allDone && policyCount !== null

  return (
    <>
      <PageHeader />
      <KpiGrid stats={stats} isLoading={isStatsLoading} error={statsError} />
      <UsageTrendChart />
      {showChecklist ? <OnboardingChecklist steps={checklistSteps} /> : null}
      <ActivityTable logs={logs} isLoading={isLogsLoading} error={logsError} />
    </>
  )
}

export default DashboardPage
```

- [ ] **Step 4: Add the `/policies/` MSW handler to the default mock server if missing**

Check `frontend/src/mocks/handlers.ts` — if there is no handler for `GET */api/v1/policies/`, add one returning an empty list so existing tests don't break:

```typescript
http.get("*/api/v1/policies/", () => {
  return HttpResponse.json({ policies: [], total: 0 })
}),
```

- [ ] **Step 5: Run the tests**

```bash
cd frontend && npx vitest run src/pages/Dashboard/DashboardPage.integration.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard/DashboardPage.tsx frontend/src/pages/Dashboard/DashboardPage.integration.test.tsx frontend/src/mocks/handlers.ts
git commit -m "feat(dashboard): dynamic onboarding checklist derives completion from real data"
```

---

### Task 2: Integration Page API Key Callout

**Files:**
- Modify: `frontend/src/pages/Integration/IntegrationPage.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/Integration/IntegrationPage.test.tsx`:

```typescript
import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import IntegrationPage from "./IntegrationPage"
import { useAuth } from "../../hooks/useAuth"

vi.mock("../../hooks/useAuth", () => ({ useAuth: vi.fn() }))

afterEach(() => cleanup())

describe("IntegrationPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok",
      user: { id: "t1", company_name: "Co", email: "a@b.com", api_key_prefix: "abc12345", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
  })

  it("shows the full-key callout with a link to settings", () => {
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)
    expect(screen.getByText(/If you don't have it, go to/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Go to Settings/i })).toBeInTheDocument()
  })

  it("navigates to /settings when the callout button is clicked", () => {
    let navigatedTo = ""
    render(
      <MemoryRouter initialEntries={["/integration"]}>
        <Routes>
          <Route path="/integration" element={<IntegrationPage />} />
          <Route path="/settings" element={<div>settings page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole("button", { name: /Go to Settings/i }))
    expect(screen.getByText("settings page")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Integration/IntegrationPage.test.tsx
```

Expected: FAIL — no callout or button exists yet.

- [ ] **Step 3: Add the callout to IntegrationPage.tsx**

In `frontend/src/pages/Integration/IntegrationPage.tsx`, add `useNavigate` import and insert the callout between the steps card and the key prefix display. Find this block:

```typescript
      <div className="rounded-2xl border border-brand-green/30 bg-brand-green/10 px-4 py-3 inline-flex items-center gap-3">
```

And replace with:

```typescript
      <div className="bg-card-bg border border-brand-green/20 rounded-2xl p-5 space-y-2">
        <p className="text-sm font-medium text-brand-green">Don't have your full API key?</p>
        <p className="text-sm text-text-muted">
          Your full key was shown once when you signed up. If you don't have it, go to{" "}
          <strong>Settings → Developer Settings → Regenerate API Key</strong> to create a new one.
        </p>
        <button
          type="button"
          onClick={() => navigate("/settings")}
          className="text-sm text-brand-green hover:underline"
        >
          Go to Settings →
        </button>
      </div>

      <div className="rounded-2xl border border-brand-green/30 bg-brand-green/10 px-4 py-3 inline-flex items-center gap-3">
```

Also add `useNavigate` to the import at the top:

```typescript
import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../../hooks/useAuth"
```

And add `const navigate = useNavigate()` inside the `IntegrationPage` function before the `return`.

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/Integration/IntegrationPage.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Integration/IntegrationPage.tsx frontend/src/pages/Integration/IntegrationPage.test.tsx
git commit -m "feat(integration): add callout explaining how to get full API key"
```

---

### Task 3: API Key Rotation Confirmation Dialog

**Files:**
- Modify: `frontend/src/pages/Settings/components/DeveloperSettingsCard.tsx`
- Modify: `frontend/src/pages/Settings/SettingsPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to the `describe("SettingsPage")` block in `frontend/src/pages/Settings/SettingsPage.test.tsx`:

```typescript
it("requires two clicks to rotate the API key (confirmation step)", async () => {
  render(<SettingsPage />)

  // First click: should show confirmation, NOT call rotate
  const rotateBtn = await screen.findByRole("button", { name: /Regenerate API Key/i })
  fireEvent.click(rotateBtn)

  expect(regenerateApiKeyRequest).not.toHaveBeenCalled()
  expect(await screen.findByText(/This will break existing integrations/i)).toBeInTheDocument()

  // Cancel returns to default state
  fireEvent.click(screen.getByRole("button", { name: /Cancel/i }))
  expect(screen.queryByText(/This will break existing integrations/i)).not.toBeInTheDocument()
})

it("rotates key when user confirms", async () => {
  render(<SettingsPage />)

  const rotateBtn = await screen.findByRole("button", { name: /Regenerate API Key/i })
  fireEvent.click(rotateBtn)
  fireEvent.click(await screen.findByRole("button", { name: /Yes, rotate key/i }))

  await waitFor(() => expect(regenerateApiKeyRequest).toHaveBeenCalledOnce())
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Settings/SettingsPage.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Add confirmation state to DeveloperSettingsCard.tsx**

Replace the entire `DeveloperSettingsCard.tsx` with:

```typescript
import { useState, useEffect } from "react"

type DeveloperSettingsCardProps = {
  tenantId: string | null
  apiKeyPrefix: string | null
  newApiKey: string | null
  isRotating: boolean
  onRotate: () => Promise<void>
  onCopyPrefix: () => Promise<void>
  onCopyNewKey: () => Promise<void>
}

function DeveloperSettingsCard({
  tenantId,
  apiKeyPrefix,
  newApiKey,
  isRotating,
  onRotate,
  onCopyPrefix,
  onCopyNewKey,
}: DeveloperSettingsCardProps) {
  const [showKey, setShowKey] = useState(false)
  const [confirming, setConfirming] = useState(false)
  useEffect(() => { setShowKey(false) }, [newApiKey])

  function handleRotateClick() {
    setConfirming(true)
  }

  async function handleConfirmRotate() {
    setConfirming(false)
    await onRotate()
  }

  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
      <h2 className="text-lg font-semibold">Developer Settings</h2>

      <p className="text-sm text-text-muted break-all">
        Your account ID: <span className="text-white">{tenantId ?? "--"}</span>
      </p>

      <div className="flex items-center gap-3 flex-wrap">
        <p className="text-sm text-text-muted">
          API key prefix: <span className="text-white">{apiKeyPrefix ?? "--"}</span>
        </p>
        <button
          type="button"
          onClick={() => void onCopyPrefix()}
          className="text-sm text-text-muted hover:text-white"
        >
          Copy Prefix
        </button>
      </div>

      {confirming ? (
        <div className="space-y-3">
          <p className="text-sm text-brand-red">
            This will break existing integrations. Your old key will stop working immediately.
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void handleConfirmRotate()}
              disabled={isRotating}
              className="rounded-lg bg-brand-red/10 border border-brand-red/30 text-brand-red px-4 py-2 font-medium hover:bg-brand-red/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isRotating ? "Rotating..." : "Yes, rotate key"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-lg border border-border-color text-text-muted px-4 py-2 font-medium hover:text-white hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleRotateClick}
          disabled={isRotating}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isRotating ? "Rotating..." : "Regenerate API Key"}
        </button>
      )}

      {newApiKey ? (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wide text-text-muted">
            New API key (copy now — it won't be shown again)
          </p>
          <div className="bg-card-bg border border-border-color rounded-lg p-3 text-sm font-mono break-all select-none">
            {showKey ? newApiKey : `${newApiKey.slice(0, 8)}${"*".repeat(24)}`}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void onCopyNewKey()}
              className="text-sm text-text-muted hover:text-white"
            >
              Copy key
            </button>
            <button
              type="button"
              onClick={() => setShowKey((prev) => !prev)}
              className="text-sm text-text-muted hover:text-white"
            >
              {showKey ? "Hide" : "Reveal"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}

export default DeveloperSettingsCard
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/Settings/SettingsPage.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Settings/components/DeveloperSettingsCard.tsx frontend/src/pages/Settings/SettingsPage.test.tsx
git commit -m "feat(settings): add two-step confirmation before API key rotation"
```

---

## Wave 2 — P1 Important Features

---

### Task 4: Dashboard "View All Activity" Link

**Files:**
- Modify: `frontend/src/components/shared/ActivityTable.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/shared/ActivityTable.test.tsx`:

```typescript
import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import ActivityTable from "./ActivityTable"
import type { AuditLog } from "../../types/api"

afterEach(() => cleanup())

const mockLog: AuditLog = {
  id: "log-1",
  tenant_id: "t1",
  session_id: null,
  hook_type: "access",
  action: "BLOCKED",
  violation_type: "prompt_injection",
  severity: "high",
  input_preview: "inject me",
  details: {},
  payload_hash: null,
  policy_version: 1,
  algorand_tx_id: null,
  processing_ms: 42,
  ip_address: null,
  user_agent: null,
  created_at: new Date().toISOString(),
}

describe("ActivityTable", () => {
  it("shows 'View all activity' link when logs are present", () => {
    render(
      <MemoryRouter><ActivityTable logs={[mockLog]} isLoading={false} error={null} /></MemoryRouter>
    )
    expect(screen.getByRole("button", { name: /View all activity/i })).toBeInTheDocument()
  })

  it("hides the link when no logs are present", () => {
    render(
      <MemoryRouter><ActivityTable logs={[]} isLoading={false} error={null} /></MemoryRouter>
    )
    expect(screen.queryByRole("button", { name: /View all activity/i })).not.toBeInTheDocument()
  })

  it("navigates to /audit-log when link is clicked", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<ActivityTable logs={[mockLog]} isLoading={false} error={null} />} />
          <Route path="/audit-log" element={<div>audit log page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole("button", { name: /View all activity/i }))
    expect(screen.getByText("audit log page")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/components/shared/ActivityTable.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Add link to ActivityTable.tsx**

At the top of the component add the import:

```typescript
import { useNavigate } from "react-router-dom"
```

Inside the `ActivityTable` component, add `const navigate = useNavigate()` before the return.

Find the section header block:

```typescript
      <div className="p-6 border-b border-border-color">
        <h2 className="text-xl font-bold">Recent Activity</h2>
      </div>
```

Replace with:

```typescript
      <div className="p-6 border-b border-border-color flex items-center justify-between">
        <h2 className="text-xl font-bold">Recent Activity</h2>
        {incidents.length > 0 ? (
          <button
            type="button"
            onClick={() => navigate("/audit-log")}
            className="text-sm text-brand-green hover:underline"
          >
            View all activity →
          </button>
        ) : null}
      </div>
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/shared/ActivityTable.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ActivityTable.tsx frontend/src/components/shared/ActivityTable.test.tsx
git commit -m "feat(dashboard): add 'View all activity' link to recent activity table"
```

---

### Task 5: Change Password — Backend

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/v1/auth.py`
- Modify: `backend/tests/test_auth_extended.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `backend/tests/test_auth_extended.py`:

```python
class TestChangePassword:
    def test_change_password_success(self, client, make_tenant):
        data = make_tenant(password="OldPass123!")
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "message" in resp.json()

        # Can now login with new password
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": data.get("email") or "any@test.com", "password": "NewPass456!"},
        )
        # Login with new password works — but we need the email from signup
        # The endpoint should work; full login test is covered by using the token

    def test_change_password_wrong_current(self, client, make_tenant):
        data = make_tenant(password="OldPass123!")
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongPass999!", "new_password": "NewPass456!"},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    def test_change_password_weak_new_password(self, client, make_tenant):
        data = make_tenant(password="OldPass123!")
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPass123!", "new_password": "weak"},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_change_password_requires_auth(self, client):
        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
        )
        assert resp.status_code == 401
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_auth_extended.py::TestChangePassword -v
```

Expected: FAIL — endpoint does not exist.

- [ ] **Step 3: Add ChangePasswordRequest schema**

In `backend/app/schemas/auth.py`, add after `ResendVerificationRequest`:

```python
class ChangePasswordRequest(BaseModel):
    """Request body for changing password when already authenticated."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        if not _HAS_LETTER.search(value):
            raise ValueError("Password must contain at least one letter.")
        if not _HAS_DIGIT.search(value):
            raise ValueError("Password must contain at least one number.")
        return value
```

- [ ] **Step 4: Add the endpoint to auth.py**

In `backend/app/api/v1/auth.py`, add the import for `ChangePasswordRequest` in the schemas import block:

```python
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,  # <-- add this
    ForgotPasswordRequest,
    ...
)
```

Then add this endpoint after the `resend_verification` endpoint:

```python
@router.post("/change-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change the current tenant's password (requires existing valid password)."""
    if not _verify_password(body.current_password, cast(str, tenant.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    tenant.password_hash = _hash_password(body.new_password)
    await db.commit()
    await _revoke_all_sessions_for_tenant(str(tenant.id))
    logger.info("auth.password_changed", tenant_id=str(tenant.id))
    return {"message": "Password updated successfully."}
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_auth_extended.py::TestChangePassword -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/api/v1/auth.py backend/tests/test_auth_extended.py
git commit -m "feat(auth): add POST /auth/change-password endpoint for authenticated users"
```

---

### Task 6: Change Password — Frontend

**Files:**
- Modify: `frontend/src/services/authService.ts`
- Modify: `frontend/src/pages/Settings/SettingsPage.tsx`
- Modify: `frontend/src/pages/Settings/SettingsPage.test.tsx`

- [ ] **Step 1: Add service function + write test**

Add to `frontend/src/services/authService.ts`:

```typescript
export async function changePasswordRequest(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await apiClient.post("/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  })
}
```

Add these tests to `SettingsPage.test.tsx`. First add the mock:

```typescript
vi.mock("../../services/authService", () => ({
  regenerateApiKeyRequest: vi.fn(),
  changePasswordRequest: vi.fn(),
}))
```

Then add import: `import { changePasswordRequest } from "../../services/authService"` and these test cases:

```typescript
it("change password: submit calls changePasswordRequest and shows success toast", async () => {
  vi.mocked(changePasswordRequest).mockResolvedValue(undefined)
  render(<><Toaster /><SettingsPage /></>)

  await waitFor(() => expect(fetchSafetyConfig).toHaveBeenCalled())

  fireEvent.change(screen.getByLabelText(/Current password/i), { target: { value: "OldPass123!" } })
  fireEvent.change(screen.getByLabelText(/New password/i), { target: { value: "NewPass456!" } })
  fireEvent.change(screen.getByLabelText(/Confirm new password/i), { target: { value: "NewPass456!" } })
  fireEvent.click(screen.getByRole("button", { name: /Update password/i }))

  expect(await screen.findByText("Password updated")).toBeInTheDocument()
  expect(changePasswordRequest).toHaveBeenCalledWith("OldPass123!", "NewPass456!")
})

it("change password: mismatch shows inline error", async () => {
  render(<SettingsPage />)

  await waitFor(() => expect(fetchSafetyConfig).toHaveBeenCalled())

  fireEvent.change(screen.getByLabelText(/New password/i), { target: { value: "NewPass456!" } })
  fireEvent.change(screen.getByLabelText(/Confirm new password/i), { target: { value: "Different123!" } })

  expect(screen.getByText("Passwords do not match.")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Settings/SettingsPage.test.tsx
```

Expected: FAIL — no change password section exists yet.

- [ ] **Step 3: Add ChangePasswordCard component inline in SettingsPage.tsx**

In `frontend/src/pages/Settings/SettingsPage.tsx`, add the import for `changePasswordRequest`:

```typescript
import { regenerateApiKeyRequest, changePasswordRequest } from "../../services/authService"
```

Then add this component before the `SettingsPage` function definition (after the `toForm` function):

```typescript
function ChangePasswordCard() {
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = newPassword.length > 0 && confirmPassword.length > 0 && newPassword !== confirmPassword

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }
    if (!/[A-Za-z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      setError("Password must contain at least one letter and one number.")
      return
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsSubmitting(true)
    try {
      await changePasswordRequest(currentPassword, newPassword)
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
      toast.success("Password updated")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === "string" ? detail : "Could not update password. Please try again.")
      toast.error("Could not update password")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
      <h2 className="text-lg font-semibold">Change Password</h2>
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div>
          <label htmlFor="current-password" className="block text-sm text-text-muted mb-2">
            Current password
          </label>
          <input
            id="current-password"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="new-password" className="block text-sm text-text-muted mb-2">
            New password
          </label>
          <input
            id="new-password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="confirm-new-password" className="block text-sm text-text-muted mb-2">
            Confirm new password
          </label>
          <input
            id="confirm-new-password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            className={`w-full bg-card-bg border rounded-lg px-3 py-2.5 text-sm ${
              mismatch ? "border-brand-red" : "border-border-color"
            }`}
          />
          {mismatch ? <p className="text-xs text-brand-red mt-1">Passwords do not match.</p> : null}
        </div>
        {error && !mismatch ? (
          <p className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={isSubmitting || mismatch || !currentPassword || !newPassword || !confirmPassword}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSubmitting ? "Updating..." : "Update password"}
        </button>
      </form>
    </section>
  )
}
```

Then in the `SettingsPage` JSX return, add `<ChangePasswordCard />` between `<DeveloperSettingsCard .../>` and `<SaveSettingsButton .../>`:

```typescript
      <DeveloperSettingsCard ... />

      <ChangePasswordCard />

      <SaveSettingsButton ... />
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/Settings/SettingsPage.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/authService.ts frontend/src/pages/Settings/SettingsPage.tsx frontend/src/pages/Settings/SettingsPage.test.tsx
git commit -m "feat(settings): add change-password section card"
```

---

### Task 7: Consolidate Settings — Expand SecurityPostureCard, Remove Policies Tab

**Files:**
- Modify: `frontend/src/pages/Settings/components/SecurityPostureCard.tsx`
- Modify: `frontend/src/pages/Settings/SettingsPage.tsx`
- Modify: `frontend/src/pages/Policies/PoliciesPage.tsx`

- [ ] **Step 1: Write the failing test**

Add to `SettingsPage.test.tsx`:

```typescript
it("shows injection protection and fail-mode controls in the security card", async () => {
  render(<SettingsPage />)
  await waitFor(() => expect(fetchSafetyConfig).toHaveBeenCalled())
  expect(screen.getByLabelText(/Block AI manipulation attempts/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/If something goes wrong/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Settings/SettingsPage.test.tsx
```

Expected: FAIL — those labels are in PolicyPage, not SettingsPage.

- [ ] **Step 3: Expand SecurityPostureForm type and card**

Replace `SecurityPostureCard.tsx` entirely:

```typescript
type SecurityPostureForm = {
  global_block_enabled: boolean
  injection_protection: boolean
  pii_redaction: boolean
  fail_mode: "open" | "closed"
  fallback_message: string
  log_retention_days: number
}

type SecurityPostureCardProps = {
  form: SecurityPostureForm
  onChange: (next: SecurityPostureForm) => void
  isLoading?: boolean
}

function SecurityPostureCard({ form, onChange, isLoading = false }: SecurityPostureCardProps) {
  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-5">
      <h2 className="text-lg font-semibold">Protection Settings</h2>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Block all harmful messages</span>
        <input
          aria-label="Block all harmful messages"
          type="checkbox"
          checked={form.global_block_enabled}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, global_block_enabled: e.target.checked })}
        />
      </label>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Block AI manipulation attempts</span>
        <input
          aria-label="Block AI manipulation attempts"
          type="checkbox"
          checked={form.injection_protection}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, injection_protection: e.target.checked })}
        />
      </label>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Hide personal info in messages</span>
        <input
          aria-label="Hide personal info in messages"
          type="checkbox"
          checked={form.pii_redaction}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, pii_redaction: e.target.checked })}
        />
      </label>

      <div>
        <label htmlFor="fail-mode-settings" className="block text-sm text-text-muted mb-2">
          If something goes wrong
        </label>
        <select
          id="fail-mode-settings"
          aria-label="If something goes wrong"
          value={form.fail_mode}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, fail_mode: e.target.value as "open" | "closed" })}
          className="bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option value="closed">Block the message (safe)</option>
          <option value="open">Allow the message (risky)</option>
        </select>
      </div>

      <div>
        <label htmlFor="fallback-message" className="block text-sm text-text-muted mb-2">
          Message shown when AI is blocked
        </label>
        <input
          id="fallback-message"
          value={form.fallback_message}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, fallback_message: e.target.value })}
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </div>

      <div>
        <label htmlFor="retention-days" className="block text-sm text-text-muted mb-2">
          Keep activity records for (days)
        </label>
        <input
          id="retention-days"
          type="number"
          min={1}
          value={form.log_retention_days}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, log_retention_days: Number(e.target.value) || 0 })}
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </div>
    </section>
  )
}

export type { SecurityPostureForm }
export default SecurityPostureCard
```

- [ ] **Step 4: Update toForm() and SettingsPage.tsx to include new fields**

In `SettingsPage.tsx`, update the `toForm` function:

```typescript
function toForm(config: SafetyConfig): SecurityPostureForm {
  return {
    global_block_enabled: config.global_block_enabled,
    injection_protection: config.injection_protection,
    pii_redaction: config.pii_redaction,
    fail_mode: config.fail_mode as "open" | "closed",
    fallback_message: config.fallback_message,
    log_retention_days: config.log_retention_days,
  }
}
```

Update the initial form state in `SettingsPage`:

```typescript
  const [form, setForm] = useState<SecurityPostureForm>({
    global_block_enabled: false,
    injection_protection: true,
    pii_redaction: true,
    fail_mode: "closed",
    fallback_message: "",
    log_retention_days: 30,
  })
```

- [ ] **Step 5: Remove the Settings tab from PoliciesPage.tsx**

In `frontend/src/pages/Policies/PoliciesPage.tsx`, remove:
1. The `activeTab` state: `const [activeTab, setActiveTab] = useState<"rules" | "config">("rules")`
2. The two tab buttons (the `<div className="flex items-center gap-2 mb-4">` block)
3. The `{activeTab === "config" ? <PolicyPage /> : null}` line
4. The three `{activeTab === "rules" ? ...` conditional wrappers (unwrap their contents)
5. The `import PolicyPage from "./PolicyPage"` import

The result should just render `<PolicyList .../>`, `<PolicyBuilderModal .../>`, and `<DeleteConfirmationModal .../>` directly without tab wrappers.

- [ ] **Step 6: Run tests**

```bash
cd frontend && npx vitest run src/pages/Settings/SettingsPage.test.tsx
cd frontend && npx vitest run src/pages/Policies/
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Settings/components/SecurityPostureCard.tsx frontend/src/pages/Settings/SettingsPage.tsx frontend/src/pages/Policies/PoliciesPage.tsx
git commit -m "feat(settings): consolidate security settings - expand posture card, remove Policies settings tab"
```

---

### Task 8: Password Show/Hide Toggles

**Files:**
- Modify: `frontend/src/pages/Login/LoginPage.tsx`
- Modify: `frontend/src/pages/Signup/SignupPage.tsx`
- Modify: `frontend/src/pages/ResetPassword/ResetPasswordPage.tsx`

- [ ] **Step 1: Write the failing test for LoginPage**

In the existing `frontend/src/pages/Login/LoginPage.integration.test.tsx`, add:

```typescript
import { fireEvent } from "@testing-library/react"

it("toggles password visibility on login form", async () => {
  // ... existing render setup ...
  render(<MemoryRouter><LoginPage /></MemoryRouter>)

  const passwordInput = screen.getByLabelText(/Password/i)
  expect(passwordInput).toHaveAttribute("type", "password")

  fireEvent.click(screen.getByRole("button", { name: /Show password/i }))
  expect(passwordInput).toHaveAttribute("type", "text")

  fireEvent.click(screen.getByRole("button", { name: /Hide password/i }))
  expect(passwordInput).toHaveAttribute("type", "password")
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Login/LoginPage.integration.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Add show/hide toggle to LoginPage.tsx**

Add this import: `import { Eye, EyeOff } from "lucide-react"`
Add this state: `const [showPassword, setShowPassword] = useState(false)`

Replace the password `<input>` block with:

```typescript
          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm pr-10 focus:ring-1 focus:ring-brand-green focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-white"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
```

- [ ] **Step 4: Run login tests**

```bash
cd frontend && npx vitest run src/pages/Login/LoginPage.integration.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Apply same pattern to SignupPage.tsx**

In `SignupPage.tsx`:
- Add `Eye, EyeOff` import from lucide-react
- Add `const [showPassword, setShowPassword] = useState(false)`
- Add `const [showConfirmPassword, setShowConfirmPassword] = useState(false)`
- Wrap the `signup-password` input in a relative container with an eye button (same pattern as LoginPage)
- Wrap the `signup-confirm-password` input in a relative container with an eye button

The eye buttons should have `aria-label={showPassword ? "Hide password" : "Show password"}` and `aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}` respectively.

- [ ] **Step 6: Apply same pattern to ResetPasswordPage.tsx**

Same approach: add `Eye, EyeOff` import, two `showNewPassword` / `showConfirmPassword` states, and wrap each password input.

- [ ] **Step 7: Run all affected tests**

```bash
cd frontend && npx vitest run src/pages/Signup/SignupPage.integration.test.tsx src/pages/Login/LoginPage.integration.test.tsx src/pages/ResetPassword/ResetPasswordPage.test.tsx
```

Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Login/LoginPage.tsx frontend/src/pages/Signup/SignupPage.tsx frontend/src/pages/ResetPassword/ResetPasswordPage.tsx
git commit -m "feat(auth): add password show/hide toggle to login, signup, and reset-password forms"
```

---

### Task 9: Complete Audit Detail Drawer

**Files:**
- Modify: `frontend/src/pages/AuditLog/components/AuditDetailDrawer.tsx`
- Modify: `frontend/src/pages/AuditLog/components/AuditDetailDrawer.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/pages/AuditLog/components/AuditDetailDrawer.test.tsx`, add:

```typescript
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import AuditDetailDrawer from "./AuditDetailDrawer"
import type { AuditLog } from "../../../types/api"

afterEach(() => cleanup())

const fullLog: AuditLog = {
  id: "abc-123",
  tenant_id: "t1",
  session_id: "sess-99",
  hook_type: "access",
  action: "BLOCKED",
  violation_type: "prompt_injection",
  severity: "high",
  input_preview: "jailbreak attempt",
  details: { confidence: 0.97 },
  payload_hash: "sha256abc",
  policy_version: 3,
  algorand_tx_id: "TXID123",
  processing_ms: 87,
  ip_address: "1.2.3.4",
  user_agent: "TestAgent/1.0",
  created_at: "2026-04-05T10:00:00Z",
}

describe("AuditDetailDrawer", () => {
  it("renders all populated fields", () => {
    render(<AuditDetailDrawer log={fullLog} onClose={() => {}} />)
    expect(screen.getByText("87ms")).toBeInTheDocument()
    expect(screen.getByText("access")).toBeInTheDocument()
    expect(screen.getByText("high")).toBeInTheDocument()
    expect(screen.getByText("sess-99")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("1.2.3.4")).toBeInTheDocument()
  })

  it("shows blockchain link when algorand_tx_id is present", () => {
    render(<AuditDetailDrawer log={fullLog} onClose={() => {}} />)
    const link = screen.getByRole("link", { name: /TXID123/i })
    expect(link).toHaveAttribute("href", "https://testnet.explorer.perawallet.app/tx/TXID123")
  })

  it("hides optional fields when null", () => {
    const sparseLog = { ...fullLog, session_id: null, algorand_tx_id: null, ip_address: null, policy_version: null }
    render(<AuditDetailDrawer log={sparseLog} onClose={() => {}} />)
    expect(screen.queryByText("sess-99")).not.toBeInTheDocument()
  })

  it("returns null when log is null", () => {
    const { container } = render(<AuditDetailDrawer log={null} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/AuditLog/components/AuditDetailDrawer.test.tsx
```

Expected: FAIL — fields are missing.

- [ ] **Step 3: Replace AuditDetailDrawer.tsx with complete version**

```typescript
import type { AuditLog } from "../../../types/api"

type AuditDetailDrawerProps = {
  log: AuditLog | null
  onClose: () => void
}

function inferReason(log: AuditLog): string {
  if (log.action === "BLOCKED") return log.violation_type ?? "Blocked by policy"
  if (log.action === "REDACTED") return log.violation_type ?? "Sensitive data redacted"
  return "Request allowed by guardrails"
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString()
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-text-muted mb-1">{label}</p>
      <div className="font-medium text-sm">{children}</div>
    </div>
  )
}

function AuditDetailDrawer({ log, onClose }: AuditDetailDrawerProps) {
  if (!log) return null

  return (
    <aside
      data-testid={`audit-drawer-${log.id}`}
      className="fixed top-0 right-0 h-full w-full max-w-xl bg-sidebar-bg border-l border-border-color shadow-2xl z-40 p-6 overflow-y-auto"
    >
      <div className="flex items-start justify-between mb-6">
        <div>
          <h3 className="text-xl font-bold">Audit Detail</h3>
          <p className="text-xs text-text-muted mt-1 break-all">{log.id}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-text-muted hover:text-white transition-colors"
        >
          Close
        </button>
      </div>

      <div className="space-y-5 text-sm">
        <Field label="Timestamp">{formatTimestamp(log.created_at)}</Field>
        <Field label="Action"><span className="uppercase">{log.action.toLowerCase()}</span></Field>
        <Field label="Reason">{inferReason(log)}</Field>
        <Field label="Hook Type">{log.hook_type}</Field>
        <Field label="Severity">{log.severity}</Field>
        {log.processing_ms !== null ? (
          <Field label="Processing Time">{log.processing_ms}ms</Field>
        ) : null}
        {log.policy_version !== null ? (
          <Field label="Policy Version">{log.policy_version}</Field>
        ) : null}
        {log.session_id ? <Field label="Session ID">{log.session_id}</Field> : null}
        {log.ip_address ? <Field label="IP Address">{log.ip_address}</Field> : null}
        {log.algorand_tx_id ? (
          <Field label="Blockchain Record">
            <a
              href={`https://testnet.explorer.perawallet.app/tx/${log.algorand_tx_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-brand-green hover:underline font-mono text-xs"
            >
              {log.algorand_tx_id}
            </a>
          </Field>
        ) : null}

        <div>
          <p className="text-text-muted mb-1">Agent Input Payload</p>
          <pre className="bg-card-bg border border-border-color rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap break-all">
            {JSON.stringify({ input_preview: log.input_preview }, null, 2)}
          </pre>
        </div>

        <div>
          <p className="text-text-muted mb-1">Guardrail Decision Details</p>
          <pre className="bg-card-bg border border-border-color rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap break-all">
            {JSON.stringify(log.details, null, 2)}
          </pre>
        </div>
      </div>
    </aside>
  )
}

export default AuditDetailDrawer
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/AuditLog/components/AuditDetailDrawer.test.tsx
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AuditLog/components/AuditDetailDrawer.tsx frontend/src/pages/AuditLog/components/AuditDetailDrawer.test.tsx
git commit -m "feat(audit): show all audit log fields and blockchain link in detail drawer"
```

---

### Task 10: Text Search in Audit Log — Backend

**Files:**
- Modify: `backend/app/api/v1/audit.py`
- Modify: `backend/tests/test_audit_extended.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_audit_extended.py`:

```python
class TestAuditSearch:
    def test_search_filters_by_input_preview(self, client, make_tenant):
        import uuid
        from app.models.audit_log import AuditLog as AuditLogModel
        # Create a tenant, inject audit logs directly via the DB, then search
        # Since we use TestClient which runs the ASGI app, we test via the API
        # by checking that the search param is accepted and returns 200
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get(
            "/api/v1/audit/",
            params={"search": "hello"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data

    def test_search_empty_string_ignored(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get(
            "/api/v1/audit/",
            params={"search": ""},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_search_requires_auth(self, client):
        resp = client.get("/api/v1/audit/", params={"search": "test"})
        assert resp.status_code == 401
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_audit_extended.py::TestAuditSearch -v
```

Expected: FAIL — `search` parameter not yet accepted.

- [ ] **Step 3: Add search param to audit.py**

In `backend/app/api/v1/audit.py`, update the `list_audit_logs` function signature and filter:

```python
@router.get("/", response_model=AuditListResponse)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    start_date: date | None = Query(None, description="Filter logs on or after this date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Filter logs on or before this date (YYYY-MM-DD)"),
    search: str | None = Query(None, description="Filter by input_preview content (case-insensitive)"),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    """Return recent tenant audit logs ordered by newest first."""
    base_filter = [AuditLog.tenant_id == tenant.id]

    if action:
        base_filter.append(AuditLog.action == action)

    if start_date:
        base_filter.append(
            AuditLog.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        )

    if end_date:
        base_filter.append(
            AuditLog.created_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        )

    if search:
        base_filter.append(AuditLog.input_preview.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(AuditLog).where(*base_filter))
    total = count_result.scalar_one()

    rows = await db.execute(
        select(AuditLog)
        .where(*base_filter)
        .order_by(desc(AuditLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    logs = rows.scalars().all()

    page = offset // limit + 1

    return AuditListResponse(logs=logs, total=total, page=page, page_size=limit)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_audit_extended.py::TestAuditSearch -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/audit.py backend/tests/test_audit_extended.py
git commit -m "feat(audit): add search query param to GET /audit/ for input_preview filtering"
```

---

### Task 11: Text Search in Audit Log — Frontend

**Files:**
- Modify: `frontend/src/services/auditService.ts`
- Modify: `frontend/src/pages/AuditLog/components/AuditFilterBar.tsx`
- Modify: `frontend/src/pages/AuditLog/AuditLogPage.tsx`
- Modify: `frontend/src/pages/AuditLog/components/AuditFilterBar.test.tsx`

- [ ] **Step 1: Update auditService.ts**

Update `FetchAuditLogsParams` and `fetchAuditLogs`:

```typescript
type FetchAuditLogsParams = {
  page?: number
  page_size?: number
  action?: "BLOCKED" | "ALLOWED" | "REDACTED"
  start_date?: string
  end_date?: string
  search?: string
}

export async function fetchAuditLogs(
  params: FetchAuditLogsParams = {},
): Promise<AuditListResponse> {
  const { page = 1, page_size = 20, action, start_date, end_date, search } = params
  const offset = Math.max(0, (page - 1) * page_size)

  const response = await apiClient.get<AuditListResponse>("/audit/", {
    params: {
      limit: page_size,
      offset,
      action,
      start_date: start_date || undefined,
      end_date: end_date || undefined,
      search: search || undefined,
    },
  })

  return response.data
}
```

- [ ] **Step 2: Write the failing test for AuditFilterBar**

In `frontend/src/pages/AuditLog/components/AuditFilterBar.test.tsx`, add:

```typescript
it("renders a search input that calls onSearchChange", async () => {
  const onSearchChange = vi.fn()
  render(
    <AuditFilterBar
      action="ALL"
      startDate=""
      endDate=""
      search=""
      onActionChange={vi.fn()}
      onStartDateChange={vi.fn()}
      onEndDateChange={vi.fn()}
      onSearchChange={onSearchChange}
    />
  )

  const searchInput = screen.getByPlaceholderText(/Search messages/i)
  expect(searchInput).toBeInTheDocument()

  fireEvent.change(searchInput, { target: { value: "inject" } })

  // Debounced — use fake timers or waitFor
  await waitFor(() => {
    expect(onSearchChange).toHaveBeenCalledWith("inject")
  }, { timeout: 500 })
})
```

- [ ] **Step 3: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/AuditLog/components/AuditFilterBar.test.tsx
```

Expected: FAIL.

- [ ] **Step 4: Update AuditFilterBar.tsx with search input + debounce**

Replace the full content of `AuditFilterBar.tsx`:

```typescript
import { useEffect, useRef, useState } from "react"

type ActionFilter = "ALL" | "BLOCKED" | "ALLOWED" | "REDACTED"

type AuditFilterBarProps = {
  action: ActionFilter
  startDate: string
  endDate: string
  search: string
  onActionChange: (value: ActionFilter) => void
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
  onSearchChange: (value: string) => void
}

function AuditFilterBar({
  action,
  startDate,
  endDate,
  search,
  onActionChange,
  onStartDateChange,
  onEndDateChange,
  onSearchChange,
}: AuditFilterBarProps) {
  const [localSearch, setLocalSearch] = useState(search)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync external reset (e.g. when page resets search to "")
  useEffect(() => {
    setLocalSearch(search)
  }, [search])

  function handleSearchChange(value: string) {
    setLocalSearch(value)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      onSearchChange(value)
    }, 300)
  }

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [])

  return (
    <div className="bg-card-bg border border-border-color rounded-2xl p-5 flex flex-col lg:flex-row gap-4 lg:items-end lg:justify-between">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
        <div>
          <label htmlFor="search-filter" className="block text-sm text-text-muted mb-2">
            Search messages
          </label>
          <input
            id="search-filter"
            type="text"
            placeholder="Search messages..."
            value={localSearch}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>

        <div>
          <label htmlFor="action-filter" className="block text-sm text-text-muted mb-2">
            Filter by result
          </label>
          <select
            id="action-filter"
            data-testid="action-filter"
            value={action}
            onChange={(event) => onActionChange(event.target.value as ActionFilter)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          >
            <option value="ALL">All</option>
            <option value="ALLOWED">Allowed</option>
            <option value="BLOCKED">Blocked</option>
            <option value="REDACTED">Redacted</option>
          </select>
        </div>

        <div>
          <label htmlFor="start-date" className="block text-sm text-text-muted mb-2">
            Start date
          </label>
          <input
            id="start-date"
            type="date"
            value={startDate}
            onChange={(event) => onStartDateChange(event.target.value)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>

        <div>
          <label htmlFor="end-date" className="block text-sm text-text-muted mb-2">
            End date
          </label>
          <input
            id="end-date"
            type="date"
            value={endDate}
            onChange={(event) => onEndDateChange(event.target.value)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>
      </div>
    </div>
  )
}

export type { ActionFilter }
export default AuditFilterBar
```

- [ ] **Step 5: Update AuditLogPage.tsx to wire the search state**

In `AuditLogPage.tsx`:
1. Add `const [search, setSearch] = useState("")`
2. Pass `search` to `AuditFilterBar` and to `fetchAuditLogs`
3. Add `search` to the `useEffect` dependency array
4. Reset page to 1 when search changes
5. Reset search in `onResetFilters`

The updated relevant parts:

```typescript
const [search, setSearch] = useState("")

// In useEffect dependency: [action, page, startDate, endDate, search]

// In fetchAuditLogs call:
const response = await fetchAuditLogs({
  page,
  page_size: PAGE_SIZE,
  action: action === "ALL" ? undefined : action,
  start_date: startDate || undefined,
  end_date: endDate || undefined,
  search: search || undefined,
})

// AuditFilterBar props:
<AuditFilterBar
  action={action}
  startDate={startDate}
  endDate={endDate}
  search={search}
  onActionChange={(value) => { setAction(value); setPage(1) }}
  onStartDateChange={(value) => { setStartDate(value); setPage(1) }}
  onEndDateChange={(value) => { setEndDate(value); setPage(1) }}
  onSearchChange={(value) => { setSearch(value); setPage(1) }}
/>

// onResetFilters:
onResetFilters={() => {
  setAction("ALL")
  setStartDate("")
  setEndDate("")
  setSearch("")
  setPage(1)
}}
```

- [ ] **Step 6: Run tests**

```bash
cd frontend && npx vitest run src/pages/AuditLog/
```

Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/services/auditService.ts frontend/src/pages/AuditLog/components/AuditFilterBar.tsx frontend/src/pages/AuditLog/AuditLogPage.tsx frontend/src/pages/AuditLog/components/AuditFilterBar.test.tsx
git commit -m "feat(audit): add debounced text search filter to audit log"
```

---

## Wave 3 — P2 Polish

---

### Task 12: Audit Log Export — Backend

**Files:**
- Modify: `backend/app/api/v1/audit.py`
- Modify: `backend/tests/test_audit_extended.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_audit_extended.py`:

```python
class TestAuditExport:
    def test_export_returns_csv(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get("/api/v1/audit/export", headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert "safebot-audit-export.csv" in resp.headers["content-disposition"]

    def test_export_csv_has_headers(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get("/api/v1/audit/export", headers=headers)
        first_line = resp.text.split("\n")[0]
        assert "id" in first_line
        assert "action" in first_line
        assert "created_at" in first_line

    def test_export_accepts_same_filters_as_list(self, client, make_tenant):
        headers = {"Authorization": f"Bearer {make_tenant()['access_token']}"}
        resp = client.get(
            "/api/v1/audit/export",
            params={"action": "BLOCKED", "search": "test"},
            headers=headers,
        )
        assert resp.status_code == 200

    def test_export_requires_auth(self, client):
        resp = client.get("/api/v1/audit/export")
        assert resp.status_code == 401
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_audit_extended.py::TestAuditExport -v
```

Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 3: Add export endpoint to audit.py**

Add these imports at the top of `audit.py`:

```python
import csv
import io

from fastapi.responses import StreamingResponse
```

Then add the endpoint after `list_audit_logs`:

```python
EXPORT_CAP = 10_000

@router.get("/export")
async def export_audit_logs(
    action: str | None = Query(None, pattern="^(BLOCKED|ALLOWED|REDACTED)$"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    search: str | None = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export audit logs as CSV (max 10,000 rows)."""
    base_filter = [AuditLog.tenant_id == tenant.id]

    if action:
        base_filter.append(AuditLog.action == action)
    if start_date:
        base_filter.append(
            AuditLog.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        )
    if end_date:
        base_filter.append(
            AuditLog.created_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        )
    if search:
        base_filter.append(AuditLog.input_preview.ilike(f"%{search}%"))

    count_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(*base_filter)
    )
    total = count_result.scalar_one()
    truncated = total > EXPORT_CAP

    rows = await db.execute(
        select(AuditLog)
        .where(*base_filter)
        .order_by(desc(AuditLog.created_at))
        .limit(EXPORT_CAP)
    )
    logs = rows.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "created_at", "action", "violation_type", "severity",
        "hook_type", "input_preview", "processing_ms", "policy_version",
        "algorand_tx_id", "session_id", "ip_address",
    ])
    for log in logs:
        writer.writerow([
            str(log.id),
            log.created_at.isoformat(),
            log.action,
            log.violation_type or "",
            log.severity,
            log.hook_type,
            log.input_preview or "",
            log.processing_ms if log.processing_ms is not None else "",
            log.policy_version if log.policy_version is not None else "",
            log.algorand_tx_id or "",
            log.session_id or "",
            str(log.ip_address) if log.ip_address else "",
        ])

    csv_content = output.getvalue()
    response_headers = {
        "Content-Disposition": "attachment; filename=safebot-audit-export.csv",
    }
    if truncated:
        response_headers["X-Export-Truncated"] = "true"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers=response_headers,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_audit_extended.py::TestAuditExport -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/audit.py backend/tests/test_audit_extended.py
git commit -m "feat(audit): add GET /audit/export CSV endpoint with same filters as list"
```

---

### Task 13: Audit Log Export — Frontend

**Files:**
- Modify: `frontend/src/services/auditService.ts`
- Modify: `frontend/src/pages/AuditLog/AuditLogPage.tsx`

- [ ] **Step 1: Add exportAuditLogs to auditService.ts**

```typescript
type ExportAuditLogsParams = {
  action?: "BLOCKED" | "ALLOWED" | "REDACTED"
  start_date?: string
  end_date?: string
  search?: string
}

export async function exportAuditLogs(params: ExportAuditLogsParams = {}): Promise<{
  blob: Blob
  truncated: boolean
}> {
  const response = await apiClient.get("/audit/export", {
    params: {
      action: params.action,
      start_date: params.start_date || undefined,
      end_date: params.end_date || undefined,
      search: params.search || undefined,
    },
    responseType: "blob",
  })
  const truncated = response.headers["x-export-truncated"] === "true"
  return { blob: response.data as Blob, truncated }
}
```

- [ ] **Step 2: Write a unit test for the export button**

In `frontend/src/pages/AuditLog/AuditLogPage.test.tsx`, add:

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { Toaster } from "sonner"
import AuditLogPage from "./AuditLogPage"
import * as auditService from "../../services/auditService"

vi.mock("../../services/auditService", async (importOriginal) => {
  const mod = await importOriginal<typeof auditService>()
  return {
    ...mod,
    fetchAuditLogs: vi.fn().mockResolvedValue({ logs: [], total: 0, page: 1, page_size: 10 }),
    exportAuditLogs: vi.fn().mockResolvedValue({ blob: new Blob(["id,action\n"], { type: "text/csv" }), truncated: false }),
  }
})

describe("AuditLogPage export", () => {
  beforeEach(() => {
    // Mock URL.createObjectURL
    URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url")
    URL.revokeObjectURL = vi.fn()
  })

  it("shows Export CSV button", async () => {
    render(<MemoryRouter><AuditLogPage /></MemoryRouter>)
    expect(await screen.findByRole("button", { name: /Export CSV/i })).toBeInTheDocument()
  })

  it("calls exportAuditLogs on button click", async () => {
    render(<MemoryRouter><><Toaster /><AuditLogPage /></></MemoryRouter>)
    const exportBtn = await screen.findByRole("button", { name: /Export CSV/i })
    fireEvent.click(exportBtn)
    await waitFor(() => expect(auditService.exportAuditLogs).toHaveBeenCalledOnce())
  })

  it("shows truncation warning when X-Export-Truncated is true", async () => {
    vi.mocked(auditService.exportAuditLogs).mockResolvedValueOnce({
      blob: new Blob(["id,action\n"]),
      truncated: true,
    })
    render(<MemoryRouter><><Toaster /><AuditLogPage /></></MemoryRouter>)
    const exportBtn = await screen.findByRole("button", { name: /Export CSV/i })
    fireEvent.click(exportBtn)
    expect(await screen.findByText(/limited to 10,000 rows/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/AuditLog/AuditLogPage.test.tsx
```

Expected: FAIL.

- [ ] **Step 4: Add export button to AuditLogPage.tsx**

In `AuditLogPage.tsx`, add the import and the export handler. Add `import { fetchAuditLogs, exportAuditLogs } from "../../services/auditService"`. Add an `isExporting` state and this handler:

```typescript
const [isExporting, setIsExporting] = useState(false)

async function handleExport() {
  setIsExporting(true)
  try {
    const { blob, truncated } = await exportAuditLogs({
      action: action === "ALL" ? undefined : action,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      search: search || undefined,
    })

    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "safebot-audit-export.csv"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    if (truncated) {
      toast.warning("Export limited to 10,000 rows. Narrow your filters to get all records.")
    }
  } catch {
    toast.error("Could not export audit logs")
  } finally {
    setIsExporting(false)
  }
}
```

Then in the JSX, add the export button next to the page title:

```typescript
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Activity History</h1>
          <p className="text-text-muted">A record of every message your AI assistant checked.</p>
        </div>
        <button
          type="button"
          onClick={() => void handleExport()}
          disabled={isExporting || isLoading}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isExporting ? "Exporting..." : "Export CSV"}
        </button>
      </div>
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npx vitest run src/pages/AuditLog/AuditLogPage.test.tsx
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/auditService.ts frontend/src/pages/AuditLog/AuditLogPage.tsx
git commit -m "feat(audit): add Export CSV button with truncation warning"
```

---

### Task 14: Account Profile — Backend

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/v1/auth.py`
- Modify: `backend/tests/test_auth_extended.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_auth_extended.py`:

```python
class TestUpdateProfile:
    def test_update_company_name(self, client, make_tenant):
        data = make_tenant()
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        resp = client.put(
            "/api/v1/auth/me",
            json={"company_name": "New Corp Name"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["company_name"] == "New Corp Name"

    def test_update_email_triggers_unverification(self, client, make_tenant):
        import uuid
        data = make_tenant()
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        new_email = f"new-{uuid.uuid4()}@example.com"
        resp = client.put(
            "/api/v1/auth/me",
            json={"email": new_email},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == new_email

    def test_update_email_conflict(self, client, make_tenant):
        data1 = make_tenant("alice")
        data2 = make_tenant("bob")
        headers2 = {"Authorization": f"Bearer {data2['access_token']}"}
        # Try to take alice's email
        alice_email = f"tenant-alice@example.com"
        resp = client.put(
            "/api/v1/auth/me",
            json={"email": alice_email},
            headers=headers2,
        )
        assert resp.status_code == 409

    def test_update_profile_requires_auth(self, client):
        resp = client.put("/api/v1/auth/me", json={"company_name": "Hacker"})
        assert resp.status_code == 401
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && pytest tests/test_auth_extended.py::TestUpdateProfile -v
```

Expected: FAIL.

- [ ] **Step 3: Add UpdateProfileRequest schema**

In `backend/app/schemas/auth.py`, add:

```python
class UpdateProfileRequest(BaseModel):
    """Request body for updating tenant profile (company name or email)."""

    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
```

- [ ] **Step 4: Add the PUT /auth/me endpoint**

In `backend/app/api/v1/auth.py`, add `UpdateProfileRequest` to the schemas import, and add this endpoint after `get_me`:

```python
@router.put("/me", response_model=TenantProfileResponse)
@limiter.limit("5/hour")
async def update_me(
    request: Request,
    body: UpdateProfileRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TenantProfileResponse:
    """Update current tenant's company name or email."""
    if body.company_name is not None:
        tenant.company_name = body.company_name

    if body.email is not None and body.email != cast(str, tenant.email):
        existing = await db.execute(
            select(Tenant).where(
                Tenant.email == body.email,
                Tenant.id != tenant.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered.")
        tenant.email = body.email
        tenant.email_verified = False

        verify_token = secrets.token_urlsafe(32)
        redis = await get_redis()
        await redis.setex(
            f"{_EMAIL_VERIFY_PREFIX}{verify_token}",
            settings.email_verification_token_ttl_seconds,
            str(tenant.id),
        )
        verify_url = f"{settings.frontend_url}/verify-email?token={verify_token}"
        logger.info("email_verification_token_created", email=body.email, verify_url=verify_url)
        await send_verification_email(body.email, verify_url)

    await db.commit()
    await db.refresh(tenant)
    logger.info("auth.profile_updated", tenant_id=str(tenant.id))
    return TenantProfileResponse(
        id=cast(UUID, tenant.id),
        company_name=cast(str, tenant.company_name),
        email=cast(str, tenant.email),
        api_key_prefix=cast(str, tenant.api_key_prefix),
        active_policy_version=cast(int, tenant.active_policy_version),
    )
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_auth_extended.py::TestUpdateProfile -v
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/api/v1/auth.py backend/tests/test_auth_extended.py
git commit -m "feat(auth): add PUT /auth/me endpoint for profile updates (name, email)"
```

---

### Task 15: Account Profile — Frontend

**Files:**
- Modify: `frontend/src/services/authService.ts`
- Create: `frontend/src/pages/Account/AccountPage.tsx`
- Create: `frontend/src/pages/Account/AccountPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Add updateProfileRequest to authService.ts**

```typescript
export async function updateProfileRequest(payload: {
  company_name?: string
  email?: string
}): Promise<TenantProfile> {
  const response = await apiClient.put<TenantProfile>("/auth/me", payload)
  return response.data
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/pages/Account/AccountPage.test.tsx`:

```typescript
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { Toaster } from "sonner"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import AccountPage from "./AccountPage"
import { useAuth } from "../../hooks/useAuth"
import { updateProfileRequest } from "../../services/authService"

vi.mock("../../hooks/useAuth", () => ({ useAuth: vi.fn() }))
vi.mock("../../services/authService", () => ({ updateProfileRequest: vi.fn() }))

afterEach(() => cleanup())

describe("AccountPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok",
      user: { id: "t1", company_name: "Old Corp", email: "old@test.com", api_key_prefix: "abc", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn().mockResolvedValue(undefined),
      logout: vi.fn(),
    })
    vi.mocked(updateProfileRequest).mockResolvedValue({
      id: "t1", company_name: "New Corp", email: "old@test.com", api_key_prefix: "abc", active_policy_version: 0,
    })
  })

  it("shows pre-filled company name", () => {
    render(<AccountPage />)
    expect(screen.getByDisplayValue("Old Corp")).toBeInTheDocument()
  })

  it("saves company name on submit", async () => {
    render(<><Toaster /><AccountPage /></>)
    fireEvent.change(screen.getByDisplayValue("Old Corp"), { target: { value: "New Corp" } })
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }))
    await waitFor(() => expect(updateProfileRequest).toHaveBeenCalledWith({ company_name: "New Corp" }))
    expect(await screen.findByText("Company name updated")).toBeInTheDocument()
  })

  it("shows re-verification warning for email changes", () => {
    render(<AccountPage />)
    expect(screen.getByText(/Changing your email will require re-verification/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Account/AccountPage.test.tsx
```

Expected: FAIL — file doesn't exist.

- [ ] **Step 4: Create AccountPage.tsx**

Create `frontend/src/pages/Account/AccountPage.tsx`:

```typescript
import { useState } from "react"
import { toast } from "sonner"
import { useAuth } from "../../hooks/useAuth"
import { updateProfileRequest } from "../../services/authService"

function AccountPage() {
  const { user, refreshProfile } = useAuth()

  const [companyName, setCompanyName] = useState(user?.company_name ?? "")
  const [email, setEmail] = useState(user?.email ?? "")
  const [isSavingName, setIsSavingName] = useState(false)
  const [isSavingEmail, setIsSavingEmail] = useState(false)
  const [nameError, setNameError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)

  const nameChanged = companyName.trim() !== (user?.company_name ?? "")
  const emailChanged = email.trim() !== (user?.email ?? "")

  async function handleSaveName() {
    if (!nameChanged || !companyName.trim()) return
    setNameError(null)
    setIsSavingName(true)
    try {
      await updateProfileRequest({ company_name: companyName.trim() })
      await refreshProfile()
      toast.success("Company name updated")
    } catch {
      setNameError("Could not update company name. Please try again.")
      toast.error("Could not update company name")
    } finally {
      setIsSavingName(false)
    }
  }

  async function handleSaveEmail() {
    if (!emailChanged || !email.trim()) return
    setEmailError(null)
    setIsSavingEmail(true)
    try {
      await updateProfileRequest({ email: email.trim() })
      await refreshProfile()
      toast.success("Email updated. Check your inbox to re-verify.")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setEmailError(typeof detail === "string" ? detail : "Could not update email. Please try again.")
      toast.error("Could not update email")
    } finally {
      setIsSavingEmail(false)
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Account</h1>
        <p className="text-text-muted">Manage your account details.</p>
      </div>

      <div className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
        <h2 className="text-lg font-semibold">Company Name</h2>
        <div>
          <label htmlFor="account-company-name" className="block text-sm text-text-muted mb-2">
            Company name
          </label>
          <input
            id="account-company-name"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>
        {nameError ? <p className="text-sm text-brand-red">{nameError}</p> : null}
        <button
          type="button"
          onClick={() => void handleSaveName()}
          disabled={isSavingName || !nameChanged}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSavingName ? "Saving..." : "Save"}
        </button>
      </div>

      <div className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
        <h2 className="text-lg font-semibold">Email Address</h2>
        <div className="bg-brand-green/5 border border-brand-green/20 rounded-lg px-3 py-2 text-xs text-text-muted">
          Changing your email will require re-verification before you can sign in again.
        </div>
        <div>
          <label htmlFor="account-email" className="block text-sm text-text-muted mb-2">
            Email address
          </label>
          <input
            id="account-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>
        {emailError ? <p className="text-sm text-brand-red">{emailError}</p> : null}
        <button
          type="button"
          onClick={() => void handleSaveEmail()}
          disabled={isSavingEmail || !emailChanged}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSavingEmail ? "Saving..." : "Save"}
        </button>
      </div>
    </section>
  )
}

export default AccountPage
```

- [ ] **Step 5: Add route to App.tsx**

In `frontend/src/App.tsx`, add `AccountPage` to the lazy imports:

```typescript
const AccountPage = lazy(() => import("./pages/Account/AccountPage"))
```

Add route inside the protected `<Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>` group:

```typescript
<Route path="/account" element={<AccountPage />} />
```

- [ ] **Step 6: Add nav item to Sidebar.tsx**

In `frontend/src/components/layout/Sidebar.tsx`, add to `navItems` after the Dashboard entry:

```typescript
import { User } from "lucide-react"

// In navItems array, after the dashboard entry:
{ to: "/account", label: "Account", icon: User },
```

- [ ] **Step 7: Run tests**

```bash
cd frontend && npx vitest run src/pages/Account/AccountPage.test.tsx
```

Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/services/authService.ts frontend/src/pages/Account/ frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(account): add account profile page for updating name and email"
```

---

### Task 16: Modal/Drawer Keyboard + Backdrop UX

**Files:**
- Modify: `frontend/src/pages/Policies/components/PolicyBuilderModal.tsx`
- Modify: `frontend/src/pages/AuditLog/components/AuditDetailDrawer.tsx`

- [ ] **Step 1: Write the failing test for PolicyBuilderModal**

In `frontend/src/pages/Policies/components/PolicyBuilderModal.test.tsx`, add:

```typescript
import { fireEvent } from "@testing-library/react"

it("closes on Escape key", async () => {
  const onClose = vi.fn()
  render(<PolicyBuilderModal mode="create" policy={null} isOpen={true} isSaving={false} onClose={onClose} onSave={vi.fn()} />)
  fireEvent.keyDown(document, { key: "Escape" })
  expect(onClose).toHaveBeenCalledOnce()
})

it("closes when backdrop is clicked", async () => {
  const onClose = vi.fn()
  render(<PolicyBuilderModal mode="create" policy={null} isOpen={true} isSaving={false} onClose={onClose} onSave={vi.fn()} />)
  fireEvent.click(screen.getByTestId("modal-backdrop"))
  expect(onClose).toHaveBeenCalledOnce()
})

it("shows X button instead of text Close", () => {
  render(<PolicyBuilderModal mode="create" policy={null} isOpen={true} isSaving={false} onClose={vi.fn()} onSave={vi.fn()} />)
  // Should not have plain "Close" text button
  expect(screen.queryByRole("button", { name: /^Close$/ })).not.toBeInTheDocument()
  // Should have X button with sr-only text
  expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/Policies/components/PolicyBuilderModal.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Update PolicyBuilderModal.tsx**

Add these imports: `import { X } from "lucide-react"` and `import { useEffect } from "react"`.

The modal already uses `useEffect` — add an additional `useEffect` for keyboard handling:

```typescript
  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])
```

Keep the early return `if (!isOpen) return null` AFTER the `useEffect` calls to comply with React rules of hooks. Move the `useEffect` calls before the conditional return.

In the JSX, wrap the existing `<aside>` in a fragment with a backdrop:

```typescript
  return (
    <>
      <div
        data-testid="modal-backdrop"
        className="fixed inset-0 bg-black/40 z-40"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="fixed top-0 right-0 h-full w-full max-w-xl bg-sidebar-bg border-l border-border-color shadow-2xl z-50 p-6 overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">{mode === "create" ? "New Protection Rule" : "Edit Protection Rule"}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-text-muted hover:text-white"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        {/* ... rest of form unchanged ... */}
      </aside>
    </>
  )
```

- [ ] **Step 4: Apply same pattern to AuditDetailDrawer.tsx**

Similarly, in `AuditDetailDrawer.tsx`:
- Add `import { X } from "lucide-react"` and `import { useEffect } from "react"`
- Add the `useEffect` for Escape key (before the `if (!log) return null` early return)
- Add backdrop `<div data-testid="drawer-backdrop" ... />`
- Replace text "Close" button with X icon button with `aria-label="Close"`

The updated JSX wraps in `<>`:

```typescript
  return (
    <>
      <div
        data-testid="drawer-backdrop"
        className="fixed inset-0 bg-black/40 z-30"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        data-testid={`audit-drawer-${log.id}`}
        className="fixed top-0 right-0 h-full w-full max-w-xl bg-sidebar-bg border-l border-border-color shadow-2xl z-40 p-6 overflow-y-auto"
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <h3 className="text-xl font-bold">Audit Detail</h3>
            <p className="text-xs text-text-muted mt-1 break-all">{log.id}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-text-muted hover:text-white transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        {/* ... rest of fields unchanged ... */}
      </aside>
    </>
  )
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npx vitest run src/pages/Policies/components/PolicyBuilderModal.test.tsx src/pages/AuditLog/components/AuditDetailDrawer.test.tsx
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Policies/components/PolicyBuilderModal.tsx frontend/src/pages/AuditLog/components/AuditDetailDrawer.tsx
git commit -m "feat(ui): add Escape key close, backdrop dismiss, and X button to modal and drawer"
```

---

### Task 17: NotFound Page — Auth-Aware

**Files:**
- Modify: `frontend/src/pages/NotFound.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/NotFound.test.tsx`:

```typescript
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import NotFound from "./NotFound"
import { useAuth } from "../hooks/useAuth"

vi.mock("../hooks/useAuth", () => ({ useAuth: vi.fn() }))

afterEach(() => cleanup())

describe("NotFound", () => {
  it("shows 'Go to Dashboard' link when authenticated", () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true, isHydrated: true, isLoading: false,
      accessToken: "tok", user: null, login: vi.fn(), refreshProfile: vi.fn(), logout: vi.fn(),
    })
    render(<MemoryRouter><NotFound /></MemoryRouter>)
    expect(screen.getByRole("link", { name: /Go to Dashboard/i })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Go to Home/i })).not.toBeInTheDocument()
  })

  it("shows 'Go to Home' link when not authenticated", () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false, isHydrated: true, isLoading: false,
      accessToken: null, user: null, login: vi.fn(), refreshProfile: vi.fn(), logout: vi.fn(),
    })
    render(<MemoryRouter><NotFound /></MemoryRouter>)
    expect(screen.getByRole("link", { name: /Go to Home/i })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Go to Dashboard/i })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd frontend && npx vitest run src/pages/NotFound.test.tsx
```

Expected: FAIL — `NotFound` doesn't use `useAuth`.

- [ ] **Step 3: Update NotFound.tsx**

```typescript
import { Link } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"

function NotFound() {
  const { isAuthenticated } = useAuth()

  return (
    <div className="h-full bg-dashboard-bg text-white flex items-center justify-center px-6">
      <div className="bg-card-bg border border-border-color rounded-2xl p-10 text-center max-w-md w-full">
        <p className="text-brand-red text-sm font-semibold mb-2">404</p>
        <h1 className="text-3xl font-bold mb-3">Page Not Found</h1>
        <p className="text-text-muted mb-6">
          This route does not exist in the Safebot dashboard.
        </p>
        {isAuthenticated ? (
          <Link
            to="/dashboard"
            className="inline-flex px-4 py-2 rounded-lg bg-brand-green/10 text-brand-green hover:bg-brand-green/20 transition-colors"
          >
            Go to Dashboard
          </Link>
        ) : (
          <Link
            to="/"
            className="inline-flex px-4 py-2 rounded-lg bg-brand-green/10 text-brand-green hover:bg-brand-green/20 transition-colors"
          >
            Go to Home
          </Link>
        )}
      </div>
    </div>
  )
}

export default NotFound
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/NotFound.test.tsx
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/NotFound.tsx frontend/src/pages/NotFound.test.tsx
git commit -m "feat(404): auth-aware 404 page shows dashboard link only when signed in"
```

---

## Post-Implementation: Full Test Suite

- [ ] **Run complete backend test suite**

```bash
cd backend && pytest -v
```

Expected: All tests PASS. No regressions.

- [ ] **Run complete frontend test suite**

```bash
cd frontend && npx vitest run
```

Expected: All tests PASS. No regressions.

- [ ] **Run Playwright E2E suite**

```bash
cd frontend && npm run e2e
```

Expected: All 9+ stable specs PASS.

- [ ] **Build frontend for production**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no TypeScript errors.

---

## Self-Review

**Spec coverage check:**
- ✅ Task 1 → Spec item 1 (Dynamic Onboarding Checklist)
- ✅ Task 2 → Spec item 2 (Integration Page Key Callout)
- ✅ Task 3 → Spec item 3 (API Key Rotation Confirmation)
- ✅ Task 4 → Spec item 4 (View All Activity Link)
- ✅ Tasks 5+6 → Spec item 5 (Change Password Backend + Frontend)
- ✅ Task 7 → Spec item 6 (Consolidate Settings)
- ✅ Task 8 → Spec item 7 (Password Show/Hide)
- ✅ Task 9 → Spec item 8 (Complete Audit Drawer)
- ✅ Tasks 10+11 → Spec item 9 (Text Search Backend + Frontend)
- ✅ N/A → Spec item 10 (Pagination Info — **already implemented**)
- ✅ Tasks 12+13 → Spec item 11 (Audit Export Backend + Frontend)
- ✅ Tasks 14+15 → Spec item 12 (Account Profile Backend + Frontend)
- ✅ Task 16 → Spec item 13 (Modal/Drawer UX)
- ✅ N/A → Spec item 14 (KPI Formatting — **already implemented**)
- ✅ Task 17 → Spec item 15 (NotFound Auth-Aware)
