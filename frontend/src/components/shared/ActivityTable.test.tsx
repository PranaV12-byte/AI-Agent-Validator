import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"
import ActivityTable from "./ActivityTable"
import type { AuditLog } from "../../types/api"

afterEach(() => cleanup())

const mockLog: AuditLog = {
  id: "log-1",
  tenant_id: "t1",
  session_id: null,
  hook_type: "access",
  action: "BLOCKED",
  violation_type: "prompt_injection",
  severity: "high",
  input_preview: "inject me",
  details: {},
  payload_hash: null,
  policy_version: 1,
  algorand_tx_id: null,
  processing_ms: 42,
  ip_address: null,
  user_agent: null,
  created_at: new Date().toISOString(),
}

describe("ActivityTable", () => {
  it("shows 'View all activity' link when logs are present", () => {
    render(
      <MemoryRouter><ActivityTable logs={[mockLog]} isLoading={false} error={null} /></MemoryRouter>
    )
    expect(screen.getByRole("button", { name: /View all activity/i })).toBeInTheDocument()
  })

  it("hides the link when no logs are present", () => {
    render(
      <MemoryRouter><ActivityTable logs={[]} isLoading={false} error={null} /></MemoryRouter>
    )
    expect(screen.queryByRole("button", { name: /View all activity/i })).not.toBeInTheDocument()
  })

  it("navigates to /audit-log when link is clicked", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<ActivityTable logs={[mockLog]} isLoading={false} error={null} />} />
          <Route path="/audit-log" element={<div>audit log page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole("button", { name: /View all activity/i }))
    expect(screen.getByText("audit log page")).toBeInTheDocument()
  })
})
