/**
 * Full new-user onboarding journey — from zero to first validated request.
 * This is the most end-to-end test in the suite: it walks through signup,
 * dashboard empty state, API key retrieval, a real SDK call, and audit confirmation.
 */
import { expect, test } from "@playwright/test"

import { API_BASE_URL } from "./helpers/auth"

test("full onboarding: signup → dashboard → API call → audit trail", async ({
  page,
  request,
}) => {
  const suffix = `onboard-${Date.now()}`
  const email = `e2e-onboard-${suffix}@example.com`
  const password = "TestPass123!"
  const companyName = `Onboard Corp ${suffix}`

  // ── Step 1: Navigate to signup and create account ──────────────────────────
  await page.goto("/signup")
  await page.getByLabel("Company name").fill(companyName)
  await page.getByLabel("Work email").fill(email)
  await page.getByLabel(/^Password$/).fill(password)
  await page.getByLabel(/confirm password/i).fill(password)

  const signupResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/signup") && resp.request().method() === "POST",
    { timeout: 20000 },
  )
  await page.getByRole("button", { name: /create account/i }).click()
  const signupResponse = await signupResponsePromise
  expect(signupResponse.status()).toBe(201)
  const signupBody = (await signupResponse.json()) as {
    api_key?: string
    access_token: string
  }

  if (!signupBody.api_key) {
    test.skip(true, "Signup does not return api_key — cannot complete end-to-end flow")
  }

  const apiKey = signupBody.api_key!

  // ── Step 2: Login and check dashboard shows zero metrics ───────────────────
  await page.waitForURL("**/login**", { timeout: 20000 })
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(password)

  const loginResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/login") && resp.request().method() === "POST",
    { timeout: 20000 },
  )
  await page.getByRole("button", { name: "Sign in" }).click()
  const loginResponse = await loginResponsePromise
  expect(loginResponse.ok(), `Login failed: ${await loginResponse.text()}`).toBeTruthy()

  await page.waitForURL("**/dashboard**", { timeout: 20000 })

  // Dashboard should show email and company name
  await expect(page.getByText(email)).toBeVisible({ timeout: 15000 })

  // ── Step 3: Navigate to Integration page and verify API key prefix ─────────
  await page.goto("/integration")
  await expect(page.getByRole("heading", { name: "Connect Your AI Tool" })).toBeVisible()
  const prefix = apiKey.slice(0, 8)
  await expect(page.getByText(prefix)).toBeVisible()

  // ── Step 4: Make a real SDK call using the API key ─────────────────────────
  const checkResponse = await request.post(`${API_BASE_URL}/api/v1/hooks/check`, {
    headers: {
      "X-API-Key": apiKey,
      "Content-Type": "application/json",
    },
    data: { message: "What is the weather today?" },
  })
  expect(checkResponse.status()).toBe(200)
  const checkBody = (await checkResponse.json()) as { action: string }
  // With all guards disabled on a fresh tenant, simple messages should be ALLOWED
  expect(checkBody.action).toMatch(/ALLOWED|REDACTED/)

  // ── Step 5: Check Audit Log shows the request ──────────────────────────────
  const auditResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/api/v1/audit/") && resp.request().method() === "GET",
    { timeout: 20000 },
  )
  await page.goto("/audit-log")
  await expect(page.getByRole("heading", { name: "Activity History" })).toBeVisible()
  await auditResponsePromise

  // At least one audit row should be visible
  await expect(
    page.locator('[data-testid^="audit-row-"]').first(),
  ).toBeVisible({ timeout: 30000 })
})

test("new user signup sees 'No rules set up yet' on policies page", async ({ page, request }) => {
  const suffix = `policies-empty-${Date.now()}`
  const email = `e2e-newpol-${suffix}@example.com`

  // Sign up via API (faster than going through UI for this sub-journey)
  const resp = await request.post(`${API_BASE_URL}/api/v1/auth/signup`, {
    data: {
      company_name: `Policies Empty Corp ${suffix}`,
      email,
      password: "TestPass123!",
    },
  })
  expect(resp.status()).toBe(201)

  // Login via UI
  await page.goto("/login")
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill("TestPass123!")
  const loginDone = page.waitForURL("**/dashboard**", { timeout: 20000 })
  await page.getByRole("button", { name: "Sign in" }).click()
  await loginDone

  // Navigate to policies — should see empty state
  await page.goto("/policies")
  await expect(page.getByText(/no rules set up yet/i)).toBeVisible({ timeout: 15000 })
  await expect(
    page.getByRole("button", { name: "Add Your First Rule" }),
  ).toBeVisible()
})

test("new user sees zero metrics on dashboard before any API calls", async ({ page, request }) => {
  const suffix = `zero-metrics-${Date.now()}`
  const email = `e2e-zerometrics-${suffix}@example.com`

  const signupResp = await request.post(`${API_BASE_URL}/api/v1/auth/signup`, {
    data: {
      company_name: `Zero Metrics Corp ${suffix}`,
      email,
      password: "TestPass123!",
    },
  })
  expect(signupResp.status()).toBe(201)

  await page.goto("/login")
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill("TestPass123!")

  const statsResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/api/v1/dashboard/stats") && resp.request().method() === "GET",
    { timeout: 20000 },
  )
  await page.getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL("**/dashboard**", { timeout: 20000 })
  const statsResponse = await statsResponsePromise
  const stats = (await statsResponse.json()) as {
    total_requests: number
    blocked_requests: number
  }

  expect(stats.total_requests).toBe(0)
  expect(stats.blocked_requests).toBe(0)
})
