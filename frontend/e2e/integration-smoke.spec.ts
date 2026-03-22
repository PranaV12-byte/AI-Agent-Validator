import { expect, test } from "@playwright/test"

import { API_BASE_URL, login, seedTenant } from "./helpers/auth"

test("integration page shows api key prefix and copy controls", async ({ page, request }) => {
  const tenant = await seedTenant(request)

  const probe = await request.post(`${API_BASE_URL}/api/v1/auth/login`, {
    data: { email: tenant.email, password: tenant.password },
  })
  expect(probe.ok(), `Seeded user cannot login via API: ${await probe.text()}`).toBeTruthy()

  await login(page, tenant.email, tenant.password)

  await page.goto("/integration")

  if (!tenant.apiKey) {
    test.skip(true, "Seeded tenant does not expose api_key")
  }

  const expectedPrefix = tenant.apiKey!.slice(0, 8)

  await expect(page.getByRole("heading", { name: "Integration" })).toBeVisible()
  await expect(page.getByText(expectedPrefix)).toBeVisible()
  await expect(page.getByTestId("snippet-python-copy")).toBeVisible()
  await expect(page.getByTestId("snippet-node-copy")).toBeVisible()
})
