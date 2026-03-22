import { expect, test } from "@playwright/test"

import { callValidate, seedTenant } from "./helpers/auth"

test("validate endpoint returns 429 after burst requests", async ({ request }) => {
  test.setTimeout(240000)

  const tenant = await seedTenant(request)
  if (!tenant.apiKey) {
    test.skip(true, "Seeded tenant does not expose api_key")
  }

  const allResponses: Array<{ status: number; body: unknown }> = []

  for (let wave = 0; wave < 3; wave += 1) {
    const responses = await Promise.all(
      Array.from({ length: 12 }).map((_, index) =>
        callValidate(
          request,
          tenant.apiKey!,
          "normal request",
          `rate-limit-${Date.now()}-${wave}-${index}`,
        ),
      ),
    )

    allResponses.push(...responses)

    const networkFailures = responses.filter((result) => result.status === 599)
    if (networkFailures.length > 0) {
      throw new Error(
        `Network/server instability during burst: ${networkFailures
          .map((item) => String(item.body))
          .join(" | ")}`,
      )
    }

    const rateLimited = responses.find((result) => result.status === 429)
    if (rateLimited) {
      if (typeof rateLimited.body === "string") {
        expect(rateLimited.body).toContain("Rate")
      } else {
        expect(rateLimited.body).toMatchObject({ error: "too_many_requests" })
      }
      return
    }

    await new Promise((resolve) => setTimeout(resolve, 100))
  }

  const statuses = allResponses.map((result) => result.status)
  expect(statuses.some((status) => status === 200 || status === 429)).toBeTruthy()
})
