# Safebot — Production Readiness Audit Design

**Date:** 2026-04-05  
**Scope:** Full pre-production audit of features, UX gaps, and missing functionality  
**Approach:** Priority Waves (3 sequential waves, each fully tested before the next starts)  
**Testing:** Unit + Integration (Vitest/MSW) + E2E (Playwright)

---

## Context

Before the first production deployment, a full audit of Safebot identified 15 concrete gaps across three severity levels. Some are UX bugs that actively mislead new users (onboarding checklist always shows incomplete), some are missing table-stakes features (no change-password, no audit search), and some are polish items that improve professional quality. This spec defines all fixes structured as three sequential waves so critical items ship first.

---

## Wave 1 — P0 Production Blockers

### 1. Dynamic Onboarding Checklist

**Problem:** `DashboardPage.tsx:16-38` — four checklist steps with steps 2–4 hardcoded `done: false`. New users see a perpetually broken checklist.

**Fix:**
- Fetch `policies` in `DashboardPage` via `fetchPolicies()` (same service used in `PoliciesPage`)
- Derive completion:
  - Step 1 "Create your account": always `done: true`
  - Step 2 "Add your first protection rule": `done: policies.length > 0`
  - Step 3 "Connect your AI tool": `done: total_requests > 0`
  - Step 4 "Send a test message": `done: total_requests > 0`
- Hide checklist entirely once all 4 steps are complete (currently: only hides when `total_requests === 0`)

**Files:**
- `frontend/src/pages/Dashboard/DashboardPage.tsx` — add `fetchPolicies` call, derive step completion
- `frontend/src/services/policyService.ts` — reuse existing `fetchPolicies()`

**Tests:**
- Vitest unit: step logic with 0 policies / 0 requests, 1+ policies, 1+ requests
- Vitest integration: MSW mocks for both APIs, verify checklist states and hide-when-complete behavior

---

### 2. Integration Page — Full API Key Flow

**Problem:** `IntegrationPage.tsx` step 1 says "Copy your connection key" but shows only the 8-char `api_key_prefix`. Users cannot complete onboarding without knowing to go to Settings first.

**Fix:**
- Add a callout card between the step list and the key display:
  > "Your full API key was shown once when you signed up. If you don't have it, go to **Settings → Developer Settings → Regenerate API Key** to create a new one."
- Add a `useNavigate`-backed "Go to Settings →" button inside the callout
- Update the code snippet placeholder comment: `# Replace with your full key from Settings`

**Files:**
- `frontend/src/pages/Integration/IntegrationPage.tsx`

**Tests:**
- Vitest unit: callout renders, button exists, navigate is called on click

---

### 3. API Key Rotation — Confirmation Dialog

**Problem:** `DeveloperSettingsCard.tsx` — clicking "Regenerate API Key" immediately fires with no warning. One accidental click permanently breaks all live integrations.

**Fix:** Two-step inline confirmation state:
- Default state: "Regenerate API Key" button
- After first click: button area transforms to warning text + "Yes, rotate key" + "Cancel" buttons
- "Yes, rotate key" calls `onRotate()`; "Cancel" returns to default state
- No modal — keep it inline within the card

**Files:**
- `frontend/src/pages/Settings/components/DeveloperSettingsCard.tsx`

**Tests:**
- Vitest unit: first click transitions to confirm state; cancel returns to default; confirm calls onRotate

---

## Wave 2 — P1 Important Missing Features

### 4. Dashboard "View All Activity" Link

**Problem:** `ActivityTable.tsx` shows last 20 logs with no navigation to `/audit-log`.

**Fix:** Add a "View all activity →" link (`useNavigate`) in the "Recent Activity" section header, right-aligned. Show only when `logs.length > 0`.

**Files:**
- `frontend/src/components/shared/ActivityTable.tsx`

**Tests:**
- Vitest unit: link renders when logs are present, hidden when empty

---

### 5. Change Password from Settings

**Problem:** Authenticated users cannot change their password — they must log out and use the forgot-password email flow.

**Backend fix:** New endpoint `POST /auth/change-password`
- Auth: `get_current_tenant` (Bearer JWT)
- Body: `ChangePasswordRequest { current_password: str, new_password: str }` — validate min 8 chars, letter+number
- Logic: verify `current_password` against stored hash; if wrong → 400; update hash; revoke all refresh families
- Rate limit: `5/hour`

**Frontend fix:** New "Change Password" section card in `SettingsPage.tsx`
- Fields: Current password, New password, Confirm new password — all with show/hide toggle (see item 7)
- Same validation as Signup
- Success: toast "Password updated"
- Error: inline error message

**Files:**
- `backend/app/api/v1/auth.py` — add `change_password` endpoint
- `backend/app/schemas/auth.py` — add `ChangePasswordRequest`
- `frontend/src/services/authService.ts` — add `changePasswordRequest()`
- `frontend/src/pages/Settings/SettingsPage.tsx` — add section card

**Tests:**
- pytest: valid change, wrong current password (400), weak new password (422), rate limit
- Vitest integration: form submit flow with MSW mock for success and error states

---

### 6. Consolidate Duplicate Settings

**Problem:** Both `SettingsPage` (via `/dashboard/safety-config`) and `PoliciesPage` "Settings" tab (via `/policies/config`) expose `pii_redaction` and overlapping security toggles. Users don't know which one is canonical.

**Fix:**
- Remove the "Settings" tab from `PoliciesPage` (remove the `activeTab === "config"` branch and the tab button)
- Expand `SettingsPage` `SecurityPostureCard` to include the fields currently only in `PolicyPage`: `injection_protection`, `fail_mode`
- `SettingsPage.handleSaveSettings()` calls both `updateSafetyConfig()` and `updatePolicyConfig()` in parallel via `Promise.all`; if either fails, show an error toast and do not update local config state (leave the UI in its edited state so the user can retry)
- `SecurityPostureCard` receives all combined fields

**Files:**
- `frontend/src/pages/Policies/PoliciesPage.tsx` — remove Settings tab
- `frontend/src/pages/Settings/SettingsPage.tsx` — add injection_protection, fail_mode fields
- `frontend/src/pages/Settings/components/SecurityPostureCard.tsx` — add new fields

**Tests:**
- Vitest unit: SecurityPostureCard renders new fields; SettingsPage calls both save APIs

---

### 7. Password Show/Hide Toggle

**Problem:** No visibility toggle on any password field. Standard UX expectation.

**Fix:** Add `Eye` / `EyeOff` (lucide-react) icon button inside each password input wrapper, toggling `type="password"` ↔ `type="text"`. Applied consistently to:
- `LoginPage.tsx` — 1 field (password)
- `SignupPage.tsx` — 2 fields (password, confirm password)
- `ResetPasswordPage.tsx` — 2 fields (new password, confirm)
- New change-password card in SettingsPage — 3 fields

**Files:** All four pages above

**Tests:**
- Vitest unit per page: toggle changes input type

---

### 8. Complete Audit Detail Drawer

**Problem:** `AuditDetailDrawer.tsx` omits most fields in the `AuditLog` type.

**Fix:** Add all populated fields in a structured layout:
- Timestamp (formatted)
- Processing Time (`processing_ms` ms)
- Hook Type
- Severity
- Session ID (if present)
- Policy Version (if present)
- IP Address (if present)
- Blockchain Record: if `algorand_tx_id`, show clickable link to `https://testnet.explorer.perawallet.app/tx/{algorand_tx_id}`

**Files:**
- `frontend/src/pages/AuditLog/components/AuditDetailDrawer.tsx`

**Tests:**
- Vitest unit: all fields render when populated; blockchain link renders only when tx_id present

---

### 9. Text Search in Audit Log

**Problem:** Audit log only supports action + date filters. Users cannot search by prompt content.

**Backend fix:** Add optional `search: str | None = Query(default=None)` to `GET /audit` — applies `AuditLog.input_preview.ilike(f"%{search}%")` when present.

**Frontend fix:** Add a text search input to `AuditFilterBar.tsx`. Debounced 300ms. Passes `search` to `fetchAuditLogs()`. Resets page to 1 on change.

**Files:**
- `backend/app/api/v1/audit.py` — add `search` query param
- `frontend/src/services/auditService.ts` — add `search` to params type
- `frontend/src/pages/AuditLog/components/AuditFilterBar.tsx` — add search input

**Tests:**
- pytest: search filters correctly, empty string ignored
- Vitest unit: debounce behavior, page reset on input

---

### 10. Pagination Info

**Problem:** `PaginationControls.tsx` shows only Prev/Next buttons with no context.

**Fix:** Add "Showing X–Y of Z results" text between the buttons. All three values (`page`, `pageSize`, `total`) are already props.

**Files:**
- `frontend/src/pages/AuditLog/components/PaginationControls.tsx`

**Tests:**
- Vitest unit: correct range text rendered for various page/pageSize/total combinations; "No results" when total = 0

---

## Wave 3 — P2 Polish

### 11. Audit Log Export (CSV)

**Backend:** New `GET /audit/export` endpoint — same filters as `GET /audit` (action, start_date, end_date, search) but returns all matching rows (cap: 10,000) as streaming CSV with `Content-Disposition: attachment; filename=safebot-audit-export.csv`. If the result set is capped, include a `X-Export-Truncated: true` response header. Frontend shows a warning toast when this header is present: "Export limited to 10,000 rows. Narrow your filters to get all records."

**Frontend:** "Export CSV" button in `AuditLogPage.tsx` header, right of filter bar. Calls export with current active filters. Triggers download via `URL.createObjectURL(blob)`. Disabled while loading.

**Files:**
- `backend/app/api/v1/audit.py` — add `/export` route
- `frontend/src/services/auditService.ts` — add `exportAuditLogs()`
- `frontend/src/pages/AuditLog/AuditLogPage.tsx` — add export button

**Tests:**
- pytest: CSV headers present, rows filtered correctly, 10k cap enforced
- Playwright E2E: apply filter → click export → verify download triggered

---

### 12. Account Profile Page

**Backend:** New `PUT /auth/me` endpoint
- Body: `UpdateProfileRequest { company_name?: str, email?: str }`
- If email changes: set `email_verified = False`, send new verification email
- Rate limit: 5/hour
- Returns updated `TenantProfileResponse`

**Frontend:** New page `/account` added to sidebar nav (between Home and Activity History)
- Section 1: Company name field + Save
- Section 2: Email field + warning "Changing email requires re-verification" + Save
- Section 3: Link "Change Password →" (scrolls/navigates to Settings)

**Files:**
- `backend/app/api/v1/auth.py` — add `update_me` endpoint
- `backend/app/schemas/auth.py` — add `UpdateProfileRequest`
- `frontend/src/services/authService.ts` — add `updateProfileRequest()`
- `frontend/src/pages/Account/AccountPage.tsx` — new page
- `frontend/src/App.tsx` — add `/account` route
- `frontend/src/components/layout/Sidebar.tsx` — add nav item

**Tests:**
- pytest: name update, email update triggers re-verification, rate limit
- Vitest integration: form save, email change warning shown

---

### 13. Modal/Drawer UX — Keyboard & Backdrop

**Problem:** `PolicyBuilderModal.tsx` and `AuditDetailDrawer.tsx` have no Escape-key close, no backdrop, and a plain text "Close" button.

**Fix (both components):**
- Replace text "Close" with an `X` icon button (`lucide-react X`)
- Add `useEffect` listening to `keydown` → `Escape` → call `onClose`; cleanup on unmount
- Add a semi-transparent backdrop `<div>` rendered behind the panel — clicking it calls `onClose`

**Files:**
- `frontend/src/pages/Policies/components/PolicyBuilderModal.tsx`
- `frontend/src/pages/AuditLog/components/AuditDetailDrawer.tsx`

**Tests:**
- Vitest unit: Escape key fires onClose; backdrop click fires onClose; X button fires onClose

---

### 14. KPI Cards — Formatting Improvements

**Problem:** `KpiGrid.tsx` shows raw numbers without context. `blocked_requests` is meaningless without a rate; `avg_latency_ms` has no units.

**Fix:**
- Add "Block rate" derived stat card: `(blocked_requests / total_requests * 100).toFixed(1) + "%"` — shown as a 4th KPI card; display "0%" when total = 0
- `avg_latency_ms`: display as `< 100ms` when under 100, otherwise `{value}ms`
- Add a short description subtitle to each KPI card (e.g. "last 30 days" or tooltip on hover)

**Files:**
- `frontend/src/components/shared/KpiGrid.tsx`

**Tests:**
- Vitest unit: block rate calculates correctly for various inputs; latency formatting; zero-division guard

---

### 15. NotFound Page — Auth-Aware Link

**Problem:** `NotFound.tsx` always links "Go to Dashboard" — unauthenticated users get redirected to login unnecessarily.

**Fix:** Read auth state via `useAuth()`. If authenticated → show "Go to Dashboard"; if not → show "Go to Home" (links to `/`).

**Files:**
- `frontend/src/pages/NotFound.tsx`

**Tests:**
- Vitest unit: authenticated user sees dashboard link; unauthenticated user sees home link

---

## Testing Strategy

| Layer | Tool | Coverage target |
|-------|------|----------------|
| Unit | Vitest + @testing-library/react | All new/modified components |
| Integration | Vitest + MSW | All new page-level flows with API mocks |
| E2E | Playwright (Chromium) | Audit export, onboarding journey, settings change-password |

E2E specs to add/update:
- `frontend/e2e/onboarding-journey.spec.ts` — verify checklist completes dynamically
- `frontend/e2e/settings-flow.spec.ts` — change password, rotate key with confirmation
- `frontend/e2e/audit-filters.spec.ts` — text search + export download

Existing CI pipeline (`ci-pr.yml`) runs all stable E2E specs on PR — add new specs to the stable list once passing.

---

## Implementation Order

1. Wave 1 items 1–3 (P0 blockers)
2. Wave 2 items 4–10 (P1 features) — items 4, 7, 10 are frontend-only and can be done in one pass
3. Wave 3 items 11–15 (P2 polish)
4. Each wave: run `make test` (backend) + `npx vitest run` (frontend) + `npm run e2e` before merging
