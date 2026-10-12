import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { AuditLog } from "../../../types/api"
import AuditTable from "./AuditTable"

afterEach(cleanup)

const baseLog: AuditLog = {
  id: "log-1",
  tenant_id: "tenant-1",
  session_id: null,
  hook_type: "access",
  action: "BLOCKED",
  violation_type: "prompt_injection",
  severity: "high",
  input_preview: "[REDACTED]",
  details: {},
  payload_hash: null,
  payload_hash_provenance: "unavailable",
  redacted_fields: [],
  anchoring_status: "disabled",
  policy_version: null,
  algorand_tx_id: null,
  processing_ms: 42,
  ip_address: null,
  user_agent: null,
  created_at: "2026-10-13T08:00:00Z",
}

function renderTable(log: AuditLog) {
  return render(
    <AuditTable
      logs={[log]}
      isLoading={false}
      error={null}
      onSelectLog={vi.fn()}
      onResetFilters={vi.fn()}
    />,
  )
}

describe("AuditTable Algorand status", () => {
  it("shows disabled status without creating an explorer link", () => {
    renderTable(baseLog)

    expect(screen.getByText("Disabled")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("does not link a legacy mock transaction even if marked anchored", () => {
    renderTable({
      ...baseLog,
      algorand_tx_id: "mock_tx_legacy",
      anchoring_status: "anchored",
    })

    expect(screen.getByText("Not anchored")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("links only a non-mock transaction with anchored status", () => {
    renderTable({
      ...baseLog,
      algorand_tx_id: "TXID123",
      anchoring_status: "anchored",
    })

    expect(screen.getByRole("link", {
      name: "Open anchored transaction in the Algorand explorer",
    })).toHaveAttribute(
      "href",
      "https://testnet.explorer.perawallet.app/tx/TXID123",
    )
  })

  it("preserves row selection when a non-link cell is clicked", () => {
    const onSelectLog = vi.fn()
    render(
      <AuditTable
        logs={[baseLog]}
        isLoading={false}
        error={null}
        onSelectLog={onSelectLog}
        onResetFilters={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByTestId("audit-row-log-1"))
    expect(onSelectLog).toHaveBeenCalledWith(baseLog)
  })
})
