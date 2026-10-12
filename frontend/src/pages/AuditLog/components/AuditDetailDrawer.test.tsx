import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import AuditDetailDrawer from "./AuditDetailDrawer"
import type { AuditLog } from "../../../types/api"

afterEach(cleanup)

const baseLog: AuditLog = {
  id: "log-abc-123",
  tenant_id: "tenant-1",
  session_id: "session-x",
  hook_type: "pre_execution",
  action: "BLOCKED",
  violation_type: "prompt_injection",
  severity: "high",
  input_preview: "Ignore all previous instructions",
  details: { reason: "prompt_injection", confidence: 0.98 },
  payload_hash: null,
  payload_hash_provenance: "unavailable",
  redacted_fields: [],
  anchoring_status: "disabled",
  policy_version: null,
  algorand_tx_id: null,
  processing_ms: 88,
  ip_address: null,
  user_agent: null,
  created_at: "2026-01-15T10:00:00Z",
}

describe("AuditDetailDrawer", () => {
  it("renders null when no log is provided", () => {
    const { container } = render(<AuditDetailDrawer log={null} onClose={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders the drawer when a log is provided", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    expect(screen.getByTestId("audit-drawer-log-abc-123")).toBeInTheDocument()
  })

  it("displays the audit log id in the header", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    expect(screen.getByText("log-abc-123")).toBeInTheDocument()
  })

  it("displays action in lowercase", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    // component renders log.action.toLowerCase()
    expect(screen.getByText("blocked")).toBeInTheDocument()
  })

  it("shows violation_type as the reason for BLOCKED action", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    expect(screen.getByText("prompt_injection")).toBeInTheDocument()
  })

  it("shows fallback reason for BLOCKED when no violation_type", () => {
    const log = { ...baseLog, violation_type: null }
    render(<AuditDetailDrawer log={log} onClose={vi.fn()} />)
    expect(screen.getByText("Blocked by policy")).toBeInTheDocument()
  })

  it("shows fallback reason for REDACTED when no violation_type", () => {
    const log = { ...baseLog, action: "REDACTED" as const, violation_type: null }
    render(<AuditDetailDrawer log={log} onClose={vi.fn()} />)
    expect(screen.getByText("Sensitive data redacted")).toBeInTheDocument()
  })

  it("shows 'Request allowed by guardrails' for ALLOWED action", () => {
    const log = { ...baseLog, action: "ALLOWED" as const, violation_type: null }
    render(<AuditDetailDrawer log={log} onClose={vi.fn()} />)
    expect(screen.getByText("Request allowed by guardrails")).toBeInTheDocument()
  })

  it("displays input_preview inside the input payload section", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    // input_preview is serialized in a JSON pre block
    expect(screen.getByText(/Ignore all previous instructions/)).toBeInTheDocument()
  })

  it("displays details as JSON in guardrail decision section", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    // Details JSON appears inside a <pre> element — use getAllByText since
    // "prompt_injection" also appears in the Reason field
    const matches = screen.getAllByText(/prompt_injection/)
    expect(matches.length).toBeGreaterThanOrEqual(2) // reason + details JSON
  })

  it("calls onClose when Close button is clicked", async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<AuditDetailDrawer log={baseLog} onClose={onClose} />)

    await user.click(screen.getByRole("button", { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("shows 'Audit Detail' heading", () => {
    render(<AuditDetailDrawer log={baseLog} onClose={vi.fn()} />)
    expect(screen.getByRole("heading", { name: /audit detail/i })).toBeInTheDocument()
  })

  it("renders all populated fields", () => {
    const fullLog: AuditLog = {
      ...baseLog,
      id: "abc-123",
      session_id: "sess-99",
      hook_type: "access",
      action: "BLOCKED",
      severity: "high",
      policy_version: 3,
      algorand_tx_id: "TXID123",
      processing_ms: 87,
      ip_address: "1.2.3.4",
      created_at: "2026-04-05T10:00:00Z",
    }
    render(<AuditDetailDrawer log={fullLog} onClose={vi.fn()} />)
    expect(screen.getByText("87ms")).toBeInTheDocument()
    expect(screen.getByText("access")).toBeInTheDocument()
    expect(screen.getByText("high")).toBeInTheDocument()
    expect(screen.getByText("sess-99")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("1.2.3.4")).toBeInTheDocument()
  })

  it("shows blockchain link when algorand_tx_id is present", () => {
    const fullLog: AuditLog = {
      ...baseLog,
      algorand_tx_id: "TXID123",
      anchoring_status: "anchored",
    }
    render(<AuditDetailDrawer log={fullLog} onClose={vi.fn()} />)
    const link = screen.getByRole("link", { name: /TXID123/i })
    expect(link).toHaveAttribute("href", "https://testnet.explorer.perawallet.app/tx/TXID123")
  })

  it("shows disabled anchoring and does not link a mock transaction", () => {
    const mockLog: AuditLog = {
      ...baseLog,
      algorand_tx_id: "mock_tx_legacy",
      anchoring_status: "disabled",
    }
    render(<AuditDetailDrawer log={mockLog} onClose={vi.fn()} />)

    expect(screen.getByText("Not anchored")).toBeInTheDocument()
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("labels stored hashes as unverified and reports display sanitization", () => {
    const log: AuditLog = {
      ...baseLog,
      payload_hash: "stored-hash-value",
      payload_hash_provenance: "stored_unverified",
      redacted_fields: ["input_preview", "details"],
    }
    render(<AuditDetailDrawer log={log} onClose={vi.fn()} />)

    expect(screen.getByText("Stored hash; not independently verified")).toBeInTheDocument()
    expect(screen.getByText("stored-hash-value")).toBeInTheDocument()
    expect(screen.getByText(/Displayed values were sanitized in: input_preview, details/)).toBeInTheDocument()
  })

  it("hides optional fields when null", () => {
    const sparseLog: AuditLog = { ...baseLog, session_id: null, algorand_tx_id: null, ip_address: null, policy_version: null }
    render(<AuditDetailDrawer log={sparseLog} onClose={vi.fn()} />)
    expect(screen.queryByText("sess-99")).not.toBeInTheDocument()
    expect(screen.queryByText("TXID123")).not.toBeInTheDocument()
  })
})
