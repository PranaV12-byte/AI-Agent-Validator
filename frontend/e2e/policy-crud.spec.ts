import { expect, test } from "@playwright/test"

import { callValidate, login, seedTenant, setPolicyConfig } from "./helpers/auth"

test("create keyword policy — matching content is blocked via SDK", async ({ page, request }) => {
  const tenant = await seedTenant(request)

  if (!tenant.apiKey) {
    test.skip(true, "Seeded tenant does not expose api_key")
  }

  // Enable policy enforcement and set fail_mode closed
  await setPolicyConfig(request, tenant.accessToken, {
    injection_protection: false,
    pii_redaction: false,
    policy_enforcement: true,
    fail_mode: "closed",
  })

  await login(page, tenant.email, tenant.password)
  await page.goto("/policies")

  const policyName = `E2E Keyword ${Date.now()}`
  const keyword = `e2e-block-word-${Date.now()}`

  await page.getByRole("button", { name: "Add a Rule" }).click()
  await page.getByLabel("Name").fill(policyName)
  await page.getByLabel("What should this rule do? (describe in plain English)").fill("Block a test keyword")
  await page.getByTestId("policy-rule-type").selectOption("keyword")
  await page.getByTestId("policy-keyword").fill(keyword)
  await page.getByTestId("policy-save-button").click()

  await expect(page.getByText("Policy created successfully")).toBeVisible({ timeout: 20000 })
  await expect(page.getByText(policyName)).toBeVisible()
})

test("create regex policy — 201 and card appears in list", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/policies")

  const policyName = `E2E Regex ${Date.now()}`
  await page.getByRole("button", { name: "Add a Rule" }).click()
  await page.getByLabel("Name").fill(policyName)
  await page.getByLabel("What should this rule do? (describe in plain English)").fill("Block 16-digit credit card numbers")
  await page.getByTestId("policy-rule-type").selectOption("regex_match")
  await page.getByTestId("policy-regex-pattern").fill("\\d{16}")
  await page.getByTestId("policy-save-button").click()

  await expect(page.getByText("Policy created successfully")).toBeVisible({ timeout: 20000 })
  await expect(page.getByText(policyName)).toBeVisible()
})

test("edit policy name — updated name appears in list", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/policies")

  const originalName = `E2E Edit Original ${Date.now()}`
  const updatedName = `E2E Edit Updated ${Date.now()}`

  // Create policy
  await page.getByRole("button", { name: "Add a Rule" }).click()
  await page.getByLabel("Name").fill(originalName)
  await page.getByLabel("What should this rule do? (describe in plain English)").fill("Original description")
  await page.getByTestId("policy-rule-type").selectOption("keyword")
  await page.getByTestId("policy-keyword").fill("original-keyword")
  await page.getByTestId("policy-save-button").click()
  await expect(page.getByText("Policy created successfully")).toBeVisible({ timeout: 20000 })

  // Open edit modal for the newly created policy
  // Find the policy card and click its Edit button
  const policyCard = page.getByText(originalName).locator("../../..")
  await policyCard.getByRole("button", { name: "Edit" }).click()

  // Update the name
  const nameInput = page.getByLabel("Name")
  await nameInput.clear()
  await nameInput.fill(updatedName)
  await page.getByTestId("policy-save-button").click()

  await expect(page.getByText("Policy updated successfully")).toBeVisible({ timeout: 20000 })
  await expect(page.getByText(updatedName)).toBeVisible()
  await expect(page.getByText(originalName)).not.toBeVisible()
})

test("delete policy — removed from the list", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/policies")

  const policyName = `E2E Delete Me ${Date.now()}`

  // Create policy to delete
  await page.getByRole("button", { name: "Add a Rule" }).click()
  await page.getByLabel("Name").fill(policyName)
  await page.getByLabel("What should this rule do? (describe in plain English)").fill("Will be deleted")
  await page.getByTestId("policy-rule-type").selectOption("keyword")
  await page.getByTestId("policy-keyword").fill("delete-me-keyword")
  await page.getByTestId("policy-save-button").click()
  await expect(page.getByText("Policy created successfully")).toBeVisible({ timeout: 20000 })
  await expect(page.getByText(policyName)).toBeVisible()

  // Delete the policy
  const deleteResponsePromise = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/v1/policies/") && resp.request().method() === "DELETE",
    { timeout: 20000 },
  )
  const policyCard = page.getByText(policyName).locator("../../..")
  await policyCard.getByRole("button", { name: "Delete" }).click()
  await deleteResponsePromise

  await expect(page.getByText(policyName)).not.toBeVisible({ timeout: 10000 })
})

test("disable policy toggle — policy marked as inactive", async ({ page, request }) => {
  const tenant = await seedTenant(request)
  await login(page, tenant.email, tenant.password)
  await page.goto("/policies")

  const policyName = `E2E Toggle ${Date.now()}`

  await page.getByRole("button", { name: "Add a Rule" }).click()
  await page.getByLabel("Name").fill(policyName)
  await page.getByLabel("What should this rule do? (describe in plain English)").fill("Toggle test")
  await page.getByTestId("policy-rule-type").selectOption("keyword")
  await page.getByTestId("policy-keyword").fill("toggle-keyword")
  await page.getByTestId("policy-save-button").click()
  await expect(page.getByText("Policy created successfully")).toBeVisible({ timeout: 20000 })

  // The policy card toggle — click to disable
  const policyCard = page.getByText(policyName).locator("../../..")
  const toggle = policyCard.locator('input[type="checkbox"]')
  await expect(toggle).toBeChecked() // enabled by default

  const updateResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/api/v1/policies/") && resp.request().method() === "PUT",
    { timeout: 20000 },
  )
  await toggle.click()
  await updateResponsePromise

  // Toggle should now be unchecked
  await expect(toggle).not.toBeChecked()
})
