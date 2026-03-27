import { render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { server } from "../../mocks/server"
import DashboardPage from "./DashboardPage"

describe("Dashboard integration", () => {
  it("hydrates metrics and ledger rows from mocked APIs", async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

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
        return HttpResponse.json({ logs: [], total: 0, page: 1, page_size: 20 })
      }),
    )

    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

    expect(await screen.findByText("Welcome to Safebot — let's get you set up")).toBeInTheDocument()
    expect(screen.getByText("Follow these steps to protect your AI assistant.")).toBeInTheDocument()
  })

  it("renders metrics error state when stats API fails", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () => {
        return HttpResponse.json({ detail: "boom" }, { status: 500 })
      }),
      http.get("*/api/v1/audit/", () => {
        return HttpResponse.json({ logs: [], total: 0, page: 1, page_size: 20 })
      }),
    )

    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

    // Allow extra time for the retry backoff (2 retries × 500ms/1000ms delays)
    expect(await screen.findByText("Unable to fetch security metrics at this time.", {}, { timeout: 5000 })).toBeInTheDocument()
  })
})
