import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const defaultModalProps = {
  mode: "create" as const,
  policy: null,
  isOpen: true,
  isSaving: false,
  onClose: vi.fn(),
  onSave: vi.fn(),
}

import PolicyBuilderModal from "./PolicyBuilderModal"

afterEach(() => {
  cleanup()
})

describe("PolicyBuilderModal", () => {
  it("renders dynamic inputs based on selected rule type", () => {
    render(
      <PolicyBuilderModal
        mode="create"
        policy={null}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const ruleType = screen.getByTestId("policy-rule-type")

    fireEvent.change(ruleType, { target: { value: "regex_match" } })
    expect(screen.getByTestId("policy-regex-pattern")).toBeInTheDocument()

    fireEvent.change(ruleType, { target: { value: "llm_eval" } })
    expect(screen.getByTestId("policy-llm-rubric")).toBeInTheDocument()
  })

  it("keeps save button disabled until required fields are valid", () => {
    render(
      <PolicyBuilderModal
        mode="create"
        policy={null}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const saveButton = screen.getByTestId("policy-save-button")
    expect(saveButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Regex policy" } })
    fireEvent.change(screen.getByLabelText("What should this rule do? (describe in plain English)"), {
      target: { value: "Detect credential leak" },
    })
    fireEvent.change(screen.getByTestId("policy-rule-type"), {
      target: { value: "regex_match" },
    })

    expect(saveButton).toBeDisabled()

    fireEvent.change(screen.getByTestId("policy-regex-pattern"), {
      target: { value: "[A-Z]{3}-\\d{4}" },
    })

    expect(saveButton).toBeEnabled()
  })

  it("closes on Escape key", () => {
    const onClose = vi.fn()
    render(<PolicyBuilderModal {...defaultModalProps} onClose={onClose} />)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("closes when backdrop is clicked", () => {
    const onClose = vi.fn()
    render(<PolicyBuilderModal {...defaultModalProps} onClose={onClose} />)
    fireEvent.click(screen.getByTestId("modal-backdrop"))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("shows X button instead of text Close", () => {
    render(<PolicyBuilderModal {...defaultModalProps} />)
    expect(screen.queryByRole("button", { name: /^Close$/ })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument()
  })

  it("preserves selected PII categories when editing and saving", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <PolicyBuilderModal
        mode="edit"
        policy={{
          id: "synthetic-pii-policy",
          tenant_id: "synthetic-tenant",
          name: "PII rule",
          description: null,
          rule_text: "Redact contact details",
          rule_type: "pii_redaction",
          parameters: { pii_types: ["email", "upi"] },
          is_enabled: true,
          version: 1,
          policy_hash: null,
          algorand_tx_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    )

    expect(screen.getByLabelText("Redact Email")).toBeChecked()
    expect(screen.getByLabelText("Redact UPI ID")).toBeChecked()
    expect(screen.getByLabelText("Redact PAN")).not.toBeChecked()
    fireEvent.click(screen.getByTestId("policy-save-button"))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0].parameters).toEqual({ pii_types: ["email", "upi"] })
  })

  it("preserves injection sensitivity when editing and saving", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <PolicyBuilderModal
        mode="edit"
        policy={{
          id: "synthetic-injection-policy",
          tenant_id: "synthetic-tenant",
          name: "Injection rule",
          description: null,
          rule_text: "Detect prompt injection",
          rule_type: "prompt_injection",
          parameters: { sensitivity: "strict" },
          is_enabled: true,
          version: 1,
          policy_hash: null,
          algorand_tx_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    )

    expect(screen.getByTestId("policy-injection-sensitivity")).toHaveValue("strict")
    fireEvent.click(screen.getByTestId("policy-save-button"))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0].parameters).toEqual({ sensitivity: "strict" })
  })

  it("preserves a semantic threshold when editing and saving", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <PolicyBuilderModal
        mode="edit"
        policy={{
          id: "synthetic-semantic-policy",
          tenant_id: "synthetic-tenant",
          name: "Meaning rule",
          description: null,
          rule_text: "Avoid disclosure of a synthetic secret",
          rule_type: "semantic",
          parameters: { threshold: 0.82 },
          is_enabled: true,
          version: 1,
          policy_hash: null,
          algorand_tx_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    )

    expect(screen.getByTestId("policy-semantic-threshold")).toHaveValue(0.82)
    fireEvent.click(screen.getByTestId("policy-save-button"))

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())
    expect(onSave.mock.calls[0][0].parameters).toEqual({ threshold: 0.82 })
  })
})
