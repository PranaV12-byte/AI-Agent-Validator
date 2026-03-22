import { expect, test } from "@playwright/test"

import { login, seedTenant } from "./helpers/auth"

test("authentication flow shows tenant in sidebar", async ({ page, request }) => {
  const tenant = await seedTenant(request)

  await login(page, tenant.email, tenant.password)

  await expect(page.getByText(tenant.companyName)).toBeVisible()
  await expect(page.getByText(tenant.email)).toBeVisible()
})
