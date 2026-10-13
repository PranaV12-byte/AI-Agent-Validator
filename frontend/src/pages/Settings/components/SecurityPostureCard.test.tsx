import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import SecurityPostureCard from "./SecurityPostureCard"
import type { SecurityPostureForm } from "./SecurityPostureCard"

afterEach(cleanup)

const defaultForm: SecurityPostureForm = {
  global_block_enabled: false,
  injection_protection: true,
  pii_redaction: false,
  fail_mode: "closed",
  fallback_message: "I cannot help with that request.",
  log_retention_days: 90,
}

describe("SecurityPostureCard", () => {
  it("renders the Protection Settings heading", () => {
    render(<SecurityPostureCard form={defaultForm} onChange={vi.fn()} />)
    expect(screen.getByRole("heading", { name: /protection settings/i })).toBeInTheDocument()
  })

  it("renders global block enabled checkbox unchecked by default", () => {
    render(<SecurityPostureCard form={{ ...defaultForm, global_block_enabled: false }} onChange={vi.fn()} />)
    expect(screen.getByLabelText("Pause all AI requests")).not.toBeChecked()
    expect(screen.getByText("Stops every request, including harmless messages. Turn off to resume.")).toBeInTheDocument()
  })

  it("renders global_block_enabled checkbox as checked when true", () => {
    render(<SecurityPostureCard form={{ ...defaultForm, global_block_enabled: true }} onChange={vi.fn()} />)
    expect(screen.getByLabelText("Pause all AI requests")).toBeChecked()
  })

  it("renders pii_redaction checkbox as checked when true", () => {
    render(<SecurityPostureCard form={{ ...defaultForm, pii_redaction: true }} onChange={vi.fn()} />)
    const checkboxes = screen.getAllByRole("checkbox")
    // Third checkbox is pii_redaction (index 2; index 1 is injection_protection)
    expect(checkboxes[2]).toBeChecked()
  })

  it("calls onChange with toggled global_block_enabled when checkbox clicked", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SecurityPostureCard form={defaultForm} onChange={onChange} />)

    const checkboxes = screen.getAllByRole("checkbox")
    await user.click(checkboxes[0])

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ global_block_enabled: true }),
    )
  })

  it("calls onChange with toggled pii_redaction when checkbox clicked", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<SecurityPostureCard form={{ ...defaultForm, pii_redaction: false }} onChange={onChange} />)

    const checkboxes = screen.getAllByRole("checkbox")
    await user.click(checkboxes[2])

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ pii_redaction: true }),
    )
  })

  it("renders fallback_message input with current value", () => {
    render(<SecurityPostureCard form={defaultForm} onChange={vi.fn()} />)
    expect(screen.getByLabelText(/message shown when ai is blocked/i)).toHaveValue(
      "I cannot help with that request.",
    )
  })

  it("calls onChange with updated fallback_message when input changes", () => {
    const onChange = vi.fn()
    render(<SecurityPostureCard form={defaultForm} onChange={onChange} />)

    const input = screen.getByLabelText(/message shown when ai is blocked/i)
    // Use fireEvent.change for controlled inputs to set the exact target value
    fireEvent.change(input, { target: { value: "Request blocked." } })

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ fallback_message: "Request blocked." }),
    )
  })

  it("renders log_retention_days input with current value", () => {
    render(<SecurityPostureCard form={defaultForm} onChange={vi.fn()} />)
    expect(screen.getByLabelText(/keep activity records/i)).toHaveValue(90)
  })

  it("calls onChange with updated log_retention_days when number input changes", () => {
    const onChange = vi.fn()
    render(<SecurityPostureCard form={defaultForm} onChange={onChange} />)

    const input = screen.getByLabelText(/keep activity records/i)
    // Use fireEvent.change for controlled number inputs to set the exact value
    fireEvent.change(input, { target: { value: "30" } })

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ log_retention_days: 30 }),
    )
  })

  it("disables all inputs when isLoading=true", () => {
    render(<SecurityPostureCard form={defaultForm} onChange={vi.fn()} isLoading={true} />)

    const checkboxes = screen.getAllByRole("checkbox")
    for (const cb of checkboxes) {
      expect(cb).toBeDisabled()
    }

    expect(screen.getByLabelText(/message shown when ai is blocked/i)).toBeDisabled()
    expect(screen.getByLabelText(/keep activity records/i)).toBeDisabled()
  })

  it("enables all inputs when isLoading=false (default)", () => {
    render(<SecurityPostureCard form={defaultForm} onChange={vi.fn()} isLoading={false} />)

    const checkboxes = screen.getAllByRole("checkbox")
    for (const cb of checkboxes) {
      expect(cb).not.toBeDisabled()
    }

    expect(screen.getByLabelText(/message shown when ai is blocked/i)).not.toBeDisabled()
    expect(screen.getByLabelText(/keep activity records/i)).not.toBeDisabled()
  })
})
