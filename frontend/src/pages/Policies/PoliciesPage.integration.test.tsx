import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it } from "vitest"

import { server } from "../../mocks/server"
import type { Policy } from "../../types/api"
import PoliciesPage from "./PoliciesPage"

afterEach(cleanup)

const existingPolicy: Policy = {
  id: "synthetic-policy",
  tenant_id: "synthetic-tenant",
  name: "Synthetic policy",
  description: "Test-only policy",
  rule_text: "Protect a synthetic test case",
  rule_type: "keyword",
  parameters: { keyword: "synthetic" },
  is_enabled: true,
  version: 1,
  policy_hash: null,
  algorand_tx_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

describe("PoliciesPage focus restoration", () => {
  it("returns focus to Add a Rule when a successful edit reload removes its opener", async () => {
    const user = userEvent.setup()
    let fetchCount = 0
    let releaseReload!: () => void
    let reloadStarted = false
    const reloadBarrier = new Promise<void>((resolve) => {
      releaseReload = resolve
    })

    server.use(
      http.get("*/api/v1/policies/", async () => {
        fetchCount += 1
        if (fetchCount > 1) {
          reloadStarted = true
          await reloadBarrier
        }
        return HttpResponse.json({ policies: [existingPolicy], total: 1 })
      }),
      http.put("*/api/v1/policies/:policyId", () => HttpResponse.json(existingPolicy)),
    )

    render(<PoliciesPage />)
    const editButton = await screen.findByRole("button", { name: "Edit" })

    try {
      await user.click(editButton)
      expect(screen.getByRole("dialog", { name: "Edit Protection Rule" })).toBeInTheDocument()
      await user.click(screen.getByRole("button", { name: "Save", exact: true }))

      await waitFor(() => expect(reloadStarted).toBe(true))
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
      expect(editButton).not.toBeInTheDocument()
      expect(screen.getByRole("button", { name: "Add a Rule" })).toHaveFocus()
    } finally {
      releaseReload()
    }
  })
})
