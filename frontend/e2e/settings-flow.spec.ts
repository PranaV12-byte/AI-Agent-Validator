import { expect, test } from "@playwright/test"

import { API_BASE_URL, login, seedTenant } from "./helpers/auth"

test("API key rotation: old key stops working, new key works", async ({ page, request }) => {
  const tenant = await seedTenant(request)

  if (!tenant.apiKey) {
    test.skip(true, "Seeded tenant does not expose api_key")
  }

  // Old key works before rotation
  const beforeResp = await request.post(`${API_BASE_URL}/api/v1/hooks/check`, {
    headers: { "X-API-Key": tenant.apiKey! },
    data: { message: "Hello before rotation" },
  })
  expect(beforeResp.status()).toBe(200)

  // Navigate to settings and rotate the key
  await login(page, tenant.email, tenant.password)
  await page.goto("/settings")

  const regenerateResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/regenerate-key") && resp.request().method() === "POST",
    { timeout: 20000 },
  )

  await page.getByRole("button", { name: "Regenerate API Key" }).click()
  const regenerateResponse = await regenerateResponsePromise
  expect(regenerateResponse.ok(), `Regenerate failed: ${await regenerateResponse.text()}`).toBeTruthy()

  const body = (await regenerateResponse.json()) as { api_key: string }
  const newKey = body.api_key

  // Old key must fail after rotation
  const afterOldKey = await request.post(`${API_BASE_URL}/api/v1/hooks/check`, {
    headers: { "X-API-Key": tenant.apiKey! },
    data: { message: "Hello with old key" },
  })
  expect(afterOldKey.status()).toBe(401)

  // New key must work
  const afterNewKey = await request.post(`${API_BASE_URL}/api/v1/hooks/check`, {
    headers: { "X-API-Key": newKey },
    data: { message: "Hello with new key" },
  })
  expect(afterNewKey.status()).toBe(200)
})

test("API key reveal toggle: masked on rotation, revealed on click", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/settings")

  const regenerateResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/auth/regenerate-key") && resp.request().method() === "POST",
    { timeout: 20000 },
  )

  await page.getByRole("button", { name: "Regenerate API Key" }).click()
  const resp = await regenerateResponsePromise
  const body = (await resp.json()) as { api_key: string }
  const newKey = body.api_key
  const first8 = newKey.slice(0, 8)

  // Should show masked key immediately (first 8 + asterisks)
  await expect(page.getByText(new RegExp(`^${first8}\\*+$`))).toBeVisible({ timeout: 10000 })

  // Click Reveal — full key should appear
  await page.getByRole("button", { name: "Reveal" }).click()
  await expect(page.getByText(newKey)).toBeVisible()

  // Click Hide — masked again
  await page.getByRole("button", { name: "Hide" }).click()
  await expect(page.getByText(new RegExp(`^${first8}\\*+$`))).toBeVisible()
})

test("safety config save persists after page reload", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/settings")

  // Wait for config to load (controls become enabled)
  await expect(
    page.getByLabel("Hide personal info in messages"),
  ).toBeEnabled({ timeout: 20000 })

  // Toggle "Block all harmful messages" to enabled
  const blockAllCheckbox = page.getByLabel("Block all harmful messages")
  const wasChecked = await blockAllCheckbox.isChecked()
  await blockAllCheckbox.click()
  expect(await blockAllCheckbox.isChecked()).toBe(!wasChecked)

  // Save settings
  const saveResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/dashboard/safety-config") && resp.request().method() === "PUT",
    { timeout: 20000 },
  )
  await page.getByRole("button", { name: /save/i }).click()
  const saveResponse = await saveResponsePromise
  expect(saveResponse.ok(), `Save failed: ${await saveResponse.text()}`).toBeTruthy()

  // Reload and verify setting persisted
  await page.goto("/settings")
  await expect(
    page.getByLabel("Block all harmful messages"),
  ).toBeEnabled({ timeout: 20000 })

  const afterReload = await page.getByLabel("Block all harmful messages").isChecked()
  expect(afterReload).toBe(!wasChecked)
})

test("save button is disabled when no changes have been made", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/settings")

  // Wait for config to load
  await expect(
    page.getByLabel("Hide personal info in messages"),
  ).toBeEnabled({ timeout: 20000 })

  // Save button should be disabled when no changes
  const saveButton = page.getByRole("button", { name: /save/i })
  await expect(saveButton).toBeDisabled({ timeout: 10000 })
})
