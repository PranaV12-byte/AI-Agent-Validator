import { expect, test } from "@playwright/test"

import { API_BASE_URL, seedTenant } from "./helpers/auth"

test("full reset flow: request → new password → re-login", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  const newPassword = "NewPass456!"

  await page.goto("/login")
  await page.getByRole("button", { name: "Forgot password?" }).click()
  await page.waitForURL("**/forgot-password**", { timeout: 10000 })

  const forgotResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/forgot-password") && resp.request().method() === "POST",
    { timeout: 20000 },
  )

  await page.getByLabel("Email address").fill(tenant.email)
  await page.getByRole("button", { name: "Send reset link" }).click()

  const forgotResponse = await forgotResponsePromise
  expect(forgotResponse.ok(), `Forgot-password API failed: ${await forgotResponse.text()}`).toBeTruthy()

  const body = (await forgotResponse.json()) as { reset_url?: string }
  if (!body.reset_url) {
    test.skip(true, "reset_url not returned — environment gate not set to test")
  }

  const resetUrl = new URL(body.reset_url!)
  await page.goto(`/reset-password${resetUrl.search}`)

  await page.getByLabel("New password", { exact: true }).fill(newPassword)
  await page.getByLabel("Confirm new password", { exact: true }).fill(newPassword)
  await page.getByRole("button", { name: /update password/i }).click()

  await page.waitForURL("**/login**", { timeout: 20000 })
  await expect(page.getByText("Password updated! Sign in with your new password.")).toBeVisible()

  await page.getByLabel("Email").fill(tenant.email)
  await page.getByLabel("Password").fill(newPassword)

  const loginResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/login") && resp.request().method() === "POST",
    { timeout: 20000 },
  )
  await page.getByRole("button", { name: "Sign in" }).click()
  const loginResponse = await loginResponsePromise
  expect(loginResponse.ok(), `Login with new password failed: ${await loginResponse.text()}`).toBeTruthy()

  await page.waitForURL("**/dashboard**", { timeout: 20000 })

  const oldLoginResp = await request.post(`${API_BASE_URL}/api/v1/auth/login`, {
    data: { email: tenant.email, password: tenant.password },
  })
  expect(oldLoginResp.status()).toBe(401)
})

test("invalid reset token shows error", async ({ page }) => {
  await page.goto("/reset-password?token=bogus-invalid-token")

  await page.getByLabel("New password", { exact: true }).fill("SomePass789!")
  await page.getByLabel("Confirm new password", { exact: true }).fill("SomePass789!")
  await page.getByRole("button", { name: /update password/i }).click()

  await expect(
    page.getByText(/expired|invalid/i),
  ).toBeVisible({ timeout: 10000 })
})
