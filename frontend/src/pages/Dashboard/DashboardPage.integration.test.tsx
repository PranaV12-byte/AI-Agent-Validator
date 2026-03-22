import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { server } from "../../mocks/server"
import DashboardPage from "./DashboardPage"

describe("Dashboard integration", () => {
  it("hydrates metrics and ledger rows from mocked APIs", async () => {
    render(<DashboardPage />)

    await waitFor(() => {
      expect(screen.getByText("Recent Activity")).toBeInTheDocument()
    })

    expect(screen.getByText("120")).toBeInTheDocument()
    expect(screen.getByText("12")).toBeInTheDocument()

    const rows = screen.getAllByRole("row")
    expect(rows.length).toBe(4)
  }, 15000)

  it("renders empty state when no dashboard traffic exists", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () => {
        return HttpResponse.json({
          total_requests: 0,
          blocked_requests: 0,
          avg_latency_ms: 0,
        })
      }),
      http.get("*/api/v1/audit/", () => {
        return HttpResponse.json([])
      }),
    )

    render(<DashboardPage />)

    const emptyStates = await screen.findAllByText("No data found")
    expect(emptyStates.length).toBeGreaterThanOrEqual(1)
    const emptyCtas = screen.getAllByText("Make your first API call to see data.")
    expect(emptyCtas.length).toBeGreaterThanOrEqual(1)
  })

  it("renders metrics error state when stats API fails", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () => {
        return HttpResponse.json({ detail: "boom" }, { status: 500 })
      }),
      http.get("*/api/v1/audit/", () => {
        return HttpResponse.json([])
      }),
    )

    render(<DashboardPage />)

    expect(await screen.findByText("Unable to fetch security metrics at this time.")).toBeInTheDocument()
  })
})
