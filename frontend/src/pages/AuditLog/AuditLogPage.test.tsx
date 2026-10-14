import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import AuditLogPage from "./AuditLogPage"
import { exportAuditLogs, fetchAuditLogs } from "../../services/auditService"
import { fetchDecisionFeedback, saveDecisionFeedback } from "../../services/testLabService"
import type { DecisionFeedback } from "../../types/api"

vi.mock("../../services/auditService", () => ({
  fetchAuditLogs: vi.fn(),
  exportAuditLogs: vi.fn(),
}))

vi.mock("../../services/testLabService", () => ({
  fetchDecisionFeedback: vi.fn().mockResolvedValue(null),
  saveDecisionFeedback: vi.fn(),
}))

const sampleLog = {
  id: "log-1",
  tenant_id: "tenant-1",
  session_id: "session-1",
  hook_type: "post_execution",
  action: "BLOCKED" as const,
  violation_type: "prompt_injection",
  severity: "high",
  input_preview: "SELECT * FROM users; --",
  details: { reason: "injection" },
  payload_hash: "hash-1",
  policy_version: 1,
  algorand_tx_id: "tx-abc",
  processing_ms: 42,
  ip_address: "127.0.0.1",
  user_agent: "vitest",
  created_at: new Date().toISOString(),
}

describe("AuditLogPage", () => {
  function renderPage() {
    return render(<MemoryRouter><AuditLogPage /></MemoryRouter>)
  }

  afterEach(cleanup)

  beforeEach(() => {
    vi.mocked(fetchAuditLogs).mockReset()
    vi.mocked(exportAuditLogs).mockReset().mockResolvedValue(undefined)
    vi.mocked(fetchDecisionFeedback).mockReset().mockResolvedValue(null)
    vi.mocked(saveDecisionFeedback).mockReset()
    vi.mocked(fetchAuditLogs).mockResolvedValue({
      logs: [sampleLog],
      total: 1,
      page: 1,
      page_size: 10,
    })
  })

  it("refetches with selected action filter", async () => {
    renderPage()

    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalledWith({
        page: 1,
        page_size: 10,
        action: undefined,
        review_status: undefined,
      })
    })

    fireEvent.change(screen.getByTestId("action-filter"), {
      target: { value: "BLOCKED" },
    })

    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        action: "BLOCKED",
        review_status: undefined,
      })
    })
  })

  it("passes the review filter to activity requests", async () => {
    renderPage()
    await screen.findByTestId("audit-row-log-1")
    fireEvent.change(screen.getByTestId("review-filter"), { target: { value: "open" } })
    await waitFor(() => expect(fetchAuditLogs).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      action: undefined,
      review_status: "open",
    }))
  })

  it("applies the same review filter to CSV export", async () => {
    renderPage()
    await screen.findByTestId("audit-row-log-1")
    fireEvent.change(screen.getByTestId("review-filter"), { target: { value: "resolved" } })
    await waitFor(() => expect(fetchAuditLogs).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      action: undefined,
      review_status: "resolved",
    }))
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }))
    expect(exportAuditLogs).toHaveBeenCalledWith({
      action: undefined,
      start_date: undefined,
      end_date: undefined,
      search: undefined,
      review_status: "resolved",
    })
  })

  it("refreshes the filtered activity list after an open review is resolved", async () => {
    let reviewSaved = false
    const savedFeedback: DecisionFeedback = {
      id: "feedback-1",
      audit_log_id: sampleLog.id,
      decision: "unsure",
      expected_action: null,
      status: "resolved",
      note: "Reviewed",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    vi.mocked(fetchAuditLogs).mockImplementation(async (params) => {
      if (reviewSaved && params.review_status === "open") {
        return { logs: [], total: 0, page: params.page ?? 1, page_size: params.page_size ?? 10 }
      }
      return { logs: [sampleLog], total: 1, page: params.page ?? 1, page_size: params.page_size ?? 10 }
    })
    vi.mocked(saveDecisionFeedback).mockImplementation(async () => {
      reviewSaved = true
      return savedFeedback
    })
    renderPage()

    await screen.findByTestId("audit-row-log-1")
    fireEvent.change(screen.getByTestId("review-filter"), { target: { value: "open" } })
    const row = await screen.findByTestId("audit-row-log-1")
    fireEvent.click(row)
    await screen.findByLabelText("Review status")
    fireEvent.change(screen.getByLabelText("Review status"), { target: { value: "resolved" } })
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }))

    await waitFor(() => expect(saveDecisionFeedback).toHaveBeenCalled())
    await waitFor(() => expect(fetchAuditLogs).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      action: undefined,
      review_status: "open",
    }))
    await waitFor(() => expect(screen.queryByTestId("audit-row-log-1")).not.toBeInTheDocument())
  })

  it("opens detail drawer when row is clicked", async () => {
    renderPage()

    const row = await screen.findByTestId("audit-row-log-1")
    fireEvent.click(row)

    expect(screen.getByTestId("audit-drawer-log-1")).toBeInTheDocument()
  })

  it("shows audit fetch error message when API call fails", async () => {
    vi.mocked(fetchAuditLogs).mockRejectedValue(new Error("network down"))

    renderPage()

    expect(await screen.findByText("Unable to load audit ledger right now.")).toBeInTheDocument()
  })
})
