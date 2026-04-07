import { expect, test } from "@playwright/test"

import { login, seedTenant } from "./helpers/auth"

test("invalid reset token shows error UI — no blank screen", async ({ page }) => {
  // Navigate directly to reset-password with a bogus token
  await page.goto("/reset-password?token=completely-invalid-token-xyz")

  await page.getByLabel("New password", { exact: true }).fill("NewPass123!")
  await page.getByLabel("Confirm new password", { exact: true }).fill("NewPass123!")
  await page.getByRole("button", { name: /update password/i }).click()

  // Should show an error message — not a blank screen
  await expect(page.getByText(/expired|invalid/i)).toBeVisible({ timeout: 15000 })
  // Page should still be functional (heading visible)
  await expect(page.getByText(/choose a new password/i)).toBeVisible()
})

test("no-token reset page shows 'Invalid reset link.' fallback", async ({ page }) => {
  // Navigate to reset-password with no token
  await page.goto("/reset-password")
  await expect(page.getByText("Invalid reset link.")).toBeVisible({ timeout: 10000 })
  await expect(page.getByRole("button", { name: /request a new reset link/i })).toBeVisible()
})

test("reset link button on error page navigates to forgot-password", async ({ page }) => {
  await page.goto("/reset-password")
  await page.getByRole("button", { name: /request a new reset link/i }).click()
  await page.waitForURL("**/forgot-password**", { timeout: 10000 })
})

test("forgot-password for unknown email returns success response (no enumeration)", async ({
  page,
}) => {
  await page.goto("/forgot-password")
  await page.getByLabel("Email address").fill("doesnotexist-xyz@example.com")
  await page.getByRole("button", { name: "Send reset link" }).click()

  // Should show success message regardless — no account enumeration
  await expect(
    page.getByText(/if that email is registered/i),
  ).toBeVisible({ timeout: 15000 })
})

test("login page shows error for wrong credentials — no crash", async ({ page }) => {
  await page.goto("/login")
  await page.getByLabel("Email").fill("nonexistent@example.com")
  await page.getByLabel("Password").fill("WrongPass999!")
  await page.getByRole("button", { name: "Sign in" }).click()

  await expect(page.getByText(/invalid|incorrect/i)).toBeVisible({ timeout: 15000 })
  // Page should remain functional
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible()
})

test("protected routes redirect to login when not authenticated", async ({ page }) => {
  // Without logging in, navigating to dashboard should redirect to login
  await page.goto("/dashboard")
  await page.waitForURL("**/login**", { timeout: 15000 })
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible()
})

test("authenticated user visiting /login is redirected to dashboard", async ({
  page,
  request,
}) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)

  // Already authenticated — visiting /login should redirect to /dashboard
  await page.goto("/login")
  await page.waitForURL("**/dashboard**", { timeout: 15000 })
  await expect(page.getByText(tenant.email)).toBeVisible({ timeout: 15000 })
})
