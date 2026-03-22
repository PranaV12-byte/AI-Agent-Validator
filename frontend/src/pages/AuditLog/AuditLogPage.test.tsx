import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AuditLogPage from "./AuditLogPage"
import { fetchAuditLogs } from "../../services/auditService"

vi.mock("../../services/auditService", () => ({
  fetchAuditLogs: vi.fn(),
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
  beforeEach(() => {
    vi.mocked(fetchAuditLogs).mockReset()
    vi.mocked(fetchAuditLogs).mockResolvedValue({
      logs: [sampleLog],
      total: 1,
      page: 1,
      page_size: 10,
    })
  })

  it("refetches with selected action filter", async () => {
    render(<AuditLogPage />)

    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalledWith({
        page: 1,
        page_size: 10,
        action: undefined,
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
      })
    })
  })

  it("opens detail drawer when row is clicked", async () => {
    render(<AuditLogPage />)

    const row = await screen.findByTestId("audit-row-log-1")
    fireEvent.click(row)

    expect(screen.getByTestId("audit-drawer-log-1")).toBeInTheDocument()
  })

  it("shows audit fetch error message when API call fails", async () => {
    vi.mocked(fetchAuditLogs).mockRejectedValue(new Error("network down"))

    render(<AuditLogPage />)

    expect(await screen.findByText("Unable to load audit ledger right now.")).toBeInTheDocument()
  })
})
