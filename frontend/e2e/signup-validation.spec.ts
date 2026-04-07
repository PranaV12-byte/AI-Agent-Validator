import { expect, test } from "@playwright/test"

import { seedTenant } from "./helpers/auth"

test("duplicate email signup shows error message", async ({ page, request }) => {
  const tenant = await seedTenant(request)

  await page.goto("/signup")
  await page.getByLabel("Company name").fill("Duplicate Corp")
  await page.getByLabel("Work email").fill(tenant.email)
  await page.getByLabel(/^Password$/).fill("TestPass123!")
  await page.getByLabel(/confirm password/i).fill("TestPass123!")
  await page.getByRole("button", { name: /create account/i }).click()

  await expect(page.getByText(/already exists/i)).toBeVisible({ timeout: 15000 })
})

test("password too short shows validation error", async ({ page }) => {
  await page.goto("/signup")
  await page.getByLabel("Company name").fill("Validation Corp")
  await page.getByLabel("Work email").fill(`validate-short-${Date.now()}@example.com`)
  await page.getByLabel(/^Password$/).fill("abc")
  await page.getByLabel(/confirm password/i).fill("abc")
  await page.getByRole("button", { name: /create account/i }).click()

  await expect(page.getByText(/at least 8 characters/i)).toBeVisible({ timeout: 10000 })
})

test("password without a letter shows validation error", async ({ page }) => {
  await page.goto("/signup")
  await page.getByLabel("Company name").fill("Validation Corp")
  await page.getByLabel("Work email").fill(`validate-nolet-${Date.now()}@example.com`)
  await page.getByLabel(/^Password$/).fill("12345678")
  await page.getByLabel(/confirm password/i).fill("12345678")
  await page.getByRole("button", { name: /create account/i }).click()

  await expect(page.getByText(/letter and one number/i)).toBeVisible({ timeout: 10000 })
})

test("password without a digit shows validation error", async ({ page }) => {
  await page.goto("/signup")
  await page.getByLabel("Company name").fill("Validation Corp")
  await page.getByLabel("Work email").fill(`validate-nodig-${Date.now()}@example.com`)
  await page.getByLabel(/^Password$/).fill("AbcdefgH")
  await page.getByLabel(/confirm password/i).fill("AbcdefgH")
  await page.getByRole("button", { name: /create account/i }).click()

  await expect(page.getByText(/letter and one number/i)).toBeVisible({ timeout: 10000 })
})

test("mismatched passwords shows validation error", async ({ page }) => {
  await page.goto("/signup")
  await page.getByLabel("Company name").fill("Validation Corp")
  await page.getByLabel("Work email").fill(`validate-mismatch-${Date.now()}@example.com`)
  await page.getByLabel(/^Password$/).fill("TestPass123!")
  await page.getByLabel(/confirm password/i).fill("DifferentPass456!")
  await page.getByRole("button", { name: /create account/i }).click()

  await expect(page.getByText(/do not match/i)).toBeVisible({ timeout: 10000 })
})

test("full signup → redirect to login", async ({ page }) => {
  const suffix = Date.now()
  await page.goto("/signup")
  await page.getByLabel("Company name").fill(`E2E Signup Corp ${suffix}`)
  await page.getByLabel("Work email").fill(`e2e-signup-${suffix}@example.com`)
  await page.getByLabel(/^Password$/).fill("TestPass123!")
  await page.getByLabel(/confirm password/i).fill("TestPass123!")

  const signupResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/signup") && resp.request().method() === "POST",
    { timeout: 20000 },
  )
  await page.getByRole("button", { name: /create account/i }).click()
  const signupResponse = await signupResponsePromise
  expect(signupResponse.status()).toBe(201)

  // After signup, page redirects to /login
  await page.waitForURL("**/login**", { timeout: 20000 })
})
