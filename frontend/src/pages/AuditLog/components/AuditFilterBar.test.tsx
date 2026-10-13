import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import AuditFilterBar from "./AuditFilterBar"

afterEach(cleanup)

const defaultProps = {
  action: "ALL" as const,
  startDate: "",
  endDate: "",
  search: "",
  onActionChange: vi.fn(),
  onStartDateChange: vi.fn(),
  onEndDateChange: vi.fn(),
  onSearchChange: vi.fn(),
}

describe("AuditFilterBar", () => {
  it("renders the action filter select", () => {
    render(<AuditFilterBar {...defaultProps} />)
    expect(screen.getByTestId("action-filter")).toBeInTheDocument()
  })

  it("renders All, Allowed, Blocked, Redacted, and Error options", () => {
    render(<AuditFilterBar {...defaultProps} />)
    const select = screen.getByTestId("action-filter") as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value)
    expect(values).toContain("ALL")
    expect(values).toContain("ALLOWED")
    expect(values).toContain("BLOCKED")
    expect(values).toContain("REDACTED")
    expect(values).toContain("ERROR")
  })

  it("renders start date and end date inputs", () => {
    render(<AuditFilterBar {...defaultProps} />)
    expect(screen.getByLabelText(/start date/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/end date/i)).toBeInTheDocument()
  })

  it("calls onActionChange with selected value when action changes", async () => {
    const user = userEvent.setup()
    const onActionChange = vi.fn()
    render(<AuditFilterBar {...defaultProps} onActionChange={onActionChange} />)

    await user.selectOptions(screen.getByTestId("action-filter"), "BLOCKED")
    expect(onActionChange).toHaveBeenCalledWith("BLOCKED")
  })

  it("allows filtering by error actions", async () => {
    const user = userEvent.setup()
    const onActionChange = vi.fn()
    render(<AuditFilterBar {...defaultProps} onActionChange={onActionChange} />)

    await user.selectOptions(screen.getByTestId("action-filter"), "ERROR")
    expect(onActionChange).toHaveBeenCalledWith("ERROR")
  })

  it("calls onStartDateChange when start date input changes", async () => {
    const user = userEvent.setup()
    const onStartDateChange = vi.fn()
    render(<AuditFilterBar {...defaultProps} onStartDateChange={onStartDateChange} />)

    const startInput = screen.getByLabelText(/start date/i)
    await user.type(startInput, "2026-01-15")
    expect(onStartDateChange).toHaveBeenCalled()
  })

  it("calls onEndDateChange when end date input changes", async () => {
    const user = userEvent.setup()
    const onEndDateChange = vi.fn()
    render(<AuditFilterBar {...defaultProps} onEndDateChange={onEndDateChange} />)

    const endInput = screen.getByLabelText(/end date/i)
    await user.type(endInput, "2026-01-31")
    expect(onEndDateChange).toHaveBeenCalled()
  })

  it("reflects current action prop value", () => {
    render(<AuditFilterBar {...defaultProps} action="BLOCKED" />)
    expect(screen.getByTestId("action-filter")).toHaveValue("BLOCKED")
  })

  it("reflects current startDate and endDate prop values", () => {
    render(<AuditFilterBar {...defaultProps} startDate="2026-01-01" endDate="2026-01-31" />)
    expect(screen.getByLabelText(/start date/i)).toHaveValue("2026-01-01")
    expect(screen.getByLabelText(/end date/i)).toHaveValue("2026-01-31")
  })

  it("renders a search input that calls onSearchChange", async () => {
    const onSearchChange = vi.fn()
    render(<AuditFilterBar {...defaultProps} onSearchChange={onSearchChange} />)

    const searchInput = screen.getByPlaceholderText(/Search messages/i)
    expect(searchInput).toBeInTheDocument()

    fireEvent.change(searchInput, { target: { value: "inject" } })

    await waitFor(() => {
      expect(onSearchChange).toHaveBeenCalledWith("inject")
    }, { timeout: 500 })
  })
})
