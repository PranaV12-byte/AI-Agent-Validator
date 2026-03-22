import { expect, type APIRequestContext, type Page } from "@playwright/test"

export const API_BASE_URL =
  process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8000"

type SeededTenant = {
  email: string
  password: string
  companyName: string
  apiKey: string | null
  accessToken: string
}

export async function seedTenant(request: APIRequestContext): Promise<SeededTenant> {
  const password = "TestPass123!"
  const attempts = 3
  let lastError = ""

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const suffix = `${Date.now()}-${Math.floor(Math.random() * 1000000)}`
    const email = `e2e-${suffix}@example.com`
    const companyName = `E2E Corp ${suffix}`

    const response = await request.post(`${API_BASE_URL}/api/v1/auth/signup`, {
      data: {
        company_name: companyName,
        email,
        password,
      },
    })

    if (response.ok()) {
      const body = (await response.json()) as {
        api_key?: string | null
        access_token: string
      }

      return {
        email,
        password,
        companyName,
        apiKey: body.api_key ?? null,
        accessToken: body.access_token,
      }
    }

    lastError = `${response.status()} ${await response.text()}`

    if (response.status() >= 500 && attempt < attempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, 350 * (attempt + 1)))
      continue
    }

    break
  }

  throw new Error(`Failed to seed tenant after ${attempts} attempts: ${lastError}`)
}

export async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login")
  await expectLoginPageReady(page)
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(password)

  const loginResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/auth/login") && response.request().method() === "POST",
    { timeout: 20000 },
  )

  await page.getByRole("button", { name: "Sign in" }).click()

  const loginResponse = await loginResponsePromise
  if (!loginResponse.ok()) {
    throw new Error(`Login API failed: ${loginResponse.status()} ${await loginResponse.text()}`)
  }

  await page.waitForURL("**/dashboard", { timeout: 20000 })
  await expect(page.getByText(email)).toBeVisible({ timeout: 20000 })
}

async function expectLoginPageReady(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded")
  await page.getByRole("button", { name: "Sign in" }).waitFor({ state: "visible", timeout: 20000 })
}

export async function setPolicyConfig(
  request: APIRequestContext,
  accessToken: string,
  payload: {
    injection_protection?: boolean
    injection_sensitivity?: "strict" | "moderate" | "lenient"
    pii_redaction?: boolean
    policy_enforcement?: boolean
    fail_mode?: "open" | "closed"
    fallback_message?: string
  },
): Promise<void> {
  const response = await request.put(`${API_BASE_URL}/api/v1/policies/config`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    data: payload,
  })

  if (!response.ok()) {
    throw new Error(`Failed to set policy config: ${response.status()} ${await response.text()}`)
  }
}

export async function callValidate(
  request: APIRequestContext,
  apiKey: string,
  prompt: string,
  userId: string,
): Promise<{ status: number; body: unknown }> {
  let response
  try {
    response = await request.post(`${API_BASE_URL}/api/v1/validate`, {
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      data: {
        prompt,
        user_id: userId,
      },
    })
  } catch (error) {
    return {
      status: 599,
      body: error instanceof Error ? error.message : "network_error",
    }
  }

  const status = response.status()
  const textBody = await response.text()

  let parsedBody: unknown = textBody
  if (textBody) {
    try {
      parsedBody = JSON.parse(textBody)
    } catch {
      parsedBody = textBody
    }
  }

  return {
    status,
    body: parsedBody,
  }
}
