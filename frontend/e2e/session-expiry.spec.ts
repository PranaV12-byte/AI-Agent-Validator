import { expect, test } from "@playwright/test"

import { login, seedTenant } from "./helpers/auth"

test("expired session redirects tenant to login", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)

  await page.goto("/dashboard")
  await expect(page.getByText("Security Overview")).toBeVisible()

  await page.context().addCookies([
    {
      name: "safebot.auth.session",
      value: JSON.stringify({ accessToken: "expired-token" }),
      path: "/",
      domain: "localhost",
      httpOnly: false,
      secure: false,
      sameSite: "Lax",
    },
  ])

  await page.evaluate(() => {
    localStorage.setItem("safebot.auth.session", JSON.stringify({ accessToken: "expired-token" }))
  })

  await page.goto("/dashboard")
  await page.waitForURL("**/login**", { timeout: 20000 })
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible()
})
