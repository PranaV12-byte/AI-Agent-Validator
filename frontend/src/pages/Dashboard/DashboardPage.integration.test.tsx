import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"
import type { DashboardDailyActivity } from "../../types/api"

afterEach(() => cleanup())

import { server } from "../../mocks/server"
import DashboardPage from "./DashboardPage"

function makeDailyTrend(
  totals: Omit<DashboardDailyActivity, "date"> = {
    allowed_requests: 0,
    redacted_requests: 0,
    blocked_requests: 0,
    error_requests: 0,
  },
): DashboardDailyActivity[] {
  const today = new Date()
  today.setUTCHours(0, 0, 0, 0)
  return Array.from({ length: 7 }, (_, index) => {
    const day = new Date(today)
    day.setUTCDate(today.getUTCDate() - 6 + index)
    return {
      date: day.toISOString().slice(0, 10),
      allowed_requests: index === 6 ? totals.allowed_requests : 0,
      redacted_requests: index === 6 ? totals.redacted_requests : 0,
      blocked_requests: index === 6 ? totals.blocked_requests : 0,
      error_requests: index === 6 ? totals.error_requests : 0,
    }
  })
}

describe("Dashboard integration", () => {
  it("hydrates metrics and ledger rows from mocked APIs", async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByText("Recent Activity")).toBeInTheDocument()
    })

    const messagesCard = screen.getByText("Messages Checked").closest('[data-purpose="kpi-card"]')
    expect(messagesCard).not.toBeNull()
    expect(within(messagesCard!).getByText("120")).toBeInTheDocument()

    const blockedLabel = screen.getAllByText("Blocked").find((element) =>
      element.closest('[data-purpose="kpi-card"]') !== null,
    )
    expect(blockedLabel).toBeDefined()
    const blockedCard = blockedLabel!.closest('[data-purpose="kpi-card"]')
    expect(blockedCard).not.toBeNull()
    expect(within(blockedCard!).getByText("12")).toBeInTheDocument()

    const activityTable = screen.getByText("Recent Activity").closest('[data-purpose="table-container"]')
    expect(activityTable).not.toBeNull()
    const rows = within(activityTable!).getAllByRole("row")
    expect(rows.length).toBe(4)
  }, 15000)

  it("renders empty state when no dashboard traffic exists", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () => {
        return HttpResponse.json({
          total_requests: 0,
          blocked_requests: 0,
          allowed_requests: 0,
          redacted_requests: 0,
          error_requests: 0,
          avg_latency_ms: 0,
          daily_trend: makeDailyTrend(),
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

  it("marks 'Add your first protection rule' done when policies exist", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () =>
        HttpResponse.json({ total_requests: 0, blocked_requests: 0, allowed_requests: 0, redacted_requests: 0, error_requests: 0, avg_latency_ms: 0, daily_trend: makeDailyTrend() })
      ),
      http.get("*/api/v1/audit/", () =>
        HttpResponse.json({ logs: [], total: 0, page: 1, page_size: 20 })
      ),
      http.get("*/api/v1/policies/", () =>
        HttpResponse.json({
          policies: [{ id: "p1", name: "Test", rule_type: "keyword", is_enabled: true }],
          total: 1,
        })
      ),
    )

    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

    // Checklist visible because total_requests is still 0
    const ruleStep = await screen.findByText("Add your first protection rule")
    expect(ruleStep).toHaveClass("line-through")
  })

  it("hides onboarding checklist when all steps complete", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () =>
        HttpResponse.json({ total_requests: 5, blocked_requests: 1, allowed_requests: 2, redacted_requests: 1, error_requests: 1, avg_latency_ms: 45, daily_trend: makeDailyTrend({ allowed_requests: 2, redacted_requests: 1, blocked_requests: 1, error_requests: 1 }) })
      ),
      http.get("*/api/v1/audit/", () =>
        HttpResponse.json({ logs: [], total: 5, page: 1, page_size: 20 })
      ),
      http.get("*/api/v1/policies/", () =>
        HttpResponse.json({
          policies: [{ id: "p1", name: "Test", rule_type: "keyword", is_enabled: true }],
          total: 1,
        })
      ),
    )

    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.queryByText("Welcome to Safebot — let's get you set up")).not.toBeInTheDocument()
    })
  })

  it("uses explicit allowed and error totals instead of deriving allowed from total minus blocked", async () => {
    server.use(
      http.get("*/api/v1/dashboard/stats", () => HttpResponse.json({
        total_requests: 5,
        blocked_requests: 1,
        allowed_requests: 2,
        redacted_requests: 1,
        error_requests: 1,
        avg_latency_ms: 45,
        daily_trend: makeDailyTrend({ allowed_requests: 2, redacted_requests: 1, blocked_requests: 1, error_requests: 1 }),
      })),
      http.get("*/api/v1/audit/", () =>
        HttpResponse.json({ logs: [], total: 0, page: 1, page_size: 20 })
      ),
    )

    render(<MemoryRouter><DashboardPage /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getAllByText("Allowed").some((element) =>
        element.closest('[data-purpose="kpi-card"]') !== null,
      )).toBe(true)
    })
    const allowedLabel = screen.getAllByText("Allowed").find((element) =>
      element.closest('[data-purpose="kpi-card"]'),
    )
    expect(allowedLabel).toBeDefined()
    expect(within(allowedLabel!.closest('[data-purpose="kpi-card"]')!).getByText("2")).toBeInTheDocument()
    const errorCard = screen.getByText("Errors")
    expect(within(errorCard.closest('[data-purpose="kpi-card"]')!).getByText("1")).toBeInTheDocument()
    expect(screen.getByText("1 redacted separately")).toBeInTheDocument()
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
