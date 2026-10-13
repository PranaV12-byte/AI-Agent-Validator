import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { Policy, PolicyCreatePayload } from "../../../types/api"

const defaultModalProps = {
  mode: "create" as const,
  policy: null,
  isOpen: true,
  isSaving: false,
  onClose: vi.fn(),
  onSave: vi.fn(),
}

import PolicyBuilderModal from "./PolicyBuilderModal"

function PolicyBuilderHarness({ onSave }: { onSave: (payload: PolicyCreatePayload) => Promise<void> }) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setIsOpen(true)}>Open rule editor</button>
      <PolicyBuilderModal
        mode="create"
        policy={null}
        isOpen={isOpen}
        isSaving={false}
        onClose={() => setIsOpen(false)}
        onSave={onSave}
      />
    </>
  )
}

function makePolicy(overrides: Partial<Policy> = {}): Policy {
  return {
    id: "synthetic-regex-policy",
    tenant_id: "synthetic-tenant",
    name: "Regex rule",
    description: null,
    rule_text: "Match a code",
    rule_type: "regex_match",
    parameters: { pattern: "[" },
    is_enabled: true,
    version: 1,
    policy_hash: null,
    algorand_tx_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

function invalidRegexResponse() {
  return {
    response: {
      status: 422,
      data: {
        detail: [{ loc: ["body"], msg: "Value error, regex_match pattern is invalid" }],
      },
    },
  }
}

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

  it("closes on native Escape cancellation", () => {
    const onClose = vi.fn()
    render(<PolicyBuilderModal {...defaultModalProps} onClose={onClose} />)
    fireEvent(screen.getByTestId("policy-builder-dialog"), new Event("cancel", { cancelable: true }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("closes when backdrop is clicked", () => {
    const onClose = vi.fn()
    render(<PolicyBuilderModal {...defaultModalProps} onClose={onClose} />)
    fireEvent.click(screen.getByTestId("policy-builder-dialog"))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it("focuses Name when opened and restores focus after Escape closes the dialog", async () => {
    const user = userEvent.setup()
    render(<PolicyBuilderHarness onSave={vi.fn().mockResolvedValue(undefined)} />)

    const opener = screen.getByRole("button", { name: "Open rule editor" })
    await user.click(opener)
    const dialog = screen.getByRole("dialog", { name: "New Protection Rule" })
    expect(screen.getByLabelText("Name")).toHaveFocus()
    expect(dialog).toHaveClass("fixed", "inset-0", "h-full", "w-full", "backdrop:bg-black/40")
    expect(dialog.querySelector(".max-w-xl")).toHaveClass("h-full")

    const closeButton = screen.getByRole("button", { name: "Close panel" })
    closeButton.focus()
    fireEvent.keyDown(closeButton, { key: "Tab", shiftKey: true })
    const cancelButton = screen.getByRole("button", { name: "Cancel" })
    expect(cancelButton).toHaveFocus()
    fireEvent.keyDown(cancelButton, { key: "Tab" })
    expect(closeButton).toHaveFocus()

    fireEvent(dialog, new Event("cancel", { cancelable: true }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(dialog).not.toHaveAttribute("open")
    expect(opener).toHaveFocus()
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

  it("shows safe pattern feedback for create validation arrays and accepts a corrected Python pattern", async () => {
    const onSave = vi.fn()
      .mockRejectedValueOnce({
        response: {
          status: 422,
          data: {
            detail: [{ loc: ["body"], msg: "Value error, regex_match pattern is invalid" }],
          },
        },
      })
      .mockResolvedValueOnce(undefined)

    render(
      <PolicyBuilderModal
        mode="create"
        policy={null}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    )
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Regex rule" } })
    fireEvent.change(screen.getByLabelText("What should this rule do? (describe in plain English)"), {
      target: { value: "Match a code" },
    })
    fireEvent.change(screen.getByTestId("policy-rule-type"), { target: { value: "regex_match" } })
    fireEvent.change(screen.getByTestId("policy-regex-pattern"), { target: { value: "[" } })
    fireEvent.click(screen.getByTestId("policy-save-button"))

    const error = await screen.findByRole("alert")
    expect(error).toHaveTextContent("Enter a valid Python regular-expression pattern.")
    expect(screen.getByTestId("policy-regex-pattern")).toHaveValue("[")
    expect(screen.getByTestId("policy-regex-pattern")).toHaveAttribute("aria-invalid", "true")
    expect(screen.getByTestId("policy-regex-pattern")).toHaveAttribute(
      "aria-describedby",
      "policy-regex-pattern-error",
    )
    expect(error.textContent).not.toContain("[")

    fireEvent.change(screen.getByTestId("policy-regex-pattern"), {
      target: { value: "(?P<code>[A-Z]{2})" },
    })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId("policy-save-button"))
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2))
    expect(onSave.mock.calls[1][0].parameters).toEqual({ pattern: "(?P<code>[A-Z]{2})" })
  })

  it("shows safe pattern feedback for edit validation strings and uses a form fallback for other errors", async () => {
    const onSave = vi.fn()
      .mockRejectedValueOnce({
        response: { status: 422, data: { detail: "regex_match pattern is invalid" } },
      })
      .mockRejectedValueOnce({
        response: {
          status: 422,
          data: { detail: [{ loc: ["body"], msg: "Value error, name cannot be blank" }] },
        },
      })

    render(
      <PolicyBuilderModal
        mode="edit"
        policy={{
          id: "synthetic-regex-policy",
          tenant_id: "synthetic-tenant",
          name: "Regex rule",
          description: null,
          rule_text: "Match a code",
          rule_type: "regex_match",
          parameters: { pattern: "[" },
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

    fireEvent.click(screen.getByTestId("policy-save-button"))
    expect(await screen.findByText("Enter a valid Python regular-expression pattern.")).toBeInTheDocument()
    expect(screen.getByTestId("policy-regex-pattern")).toHaveValue("[")

    fireEvent.change(screen.getByTestId("policy-regex-pattern"), {
      target: { value: "(?P<code>\\d{2})" },
    })
    fireEvent.click(screen.getByTestId("policy-save-button"))
    expect(await screen.findByText("Could not save policy. Please review the form and try again.")).toBeInTheDocument()
    expect(screen.queryByText("Enter a valid Python regular-expression pattern.")).not.toBeInTheDocument()
  })

  it("ignores a delayed regex error after the pattern is edited", async () => {
    const user = userEvent.setup()
    let rejectSave!: (reason: unknown) => void
    let settledSave!: Promise<void>
    const onSave = vi.fn((_payload: PolicyCreatePayload) => {
      const pendingSave = new Promise<void>((_resolve, reject) => {
        rejectSave = reject
      })
      settledSave = pendingSave.catch(() => undefined)
      return pendingSave
    })

    render(
      <PolicyBuilderModal
        mode="create"
        policy={null}
        isOpen={true}
        isSaving={false}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    )
    await user.type(screen.getByLabelText("Name"), "Regex rule")
    await user.type(
      screen.getByLabelText("What should this rule do? (describe in plain English)"),
      "Match a code",
    )
    await user.selectOptions(screen.getByTestId("policy-rule-type"), "regex_match")
    fireEvent.change(screen.getByTestId("policy-regex-pattern"), { target: { value: "[" } })
    await user.click(screen.getByTestId("policy-save-button"))
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())

    fireEvent.change(screen.getByTestId("policy-regex-pattern"), {
      target: { value: "(?P<code>[A-Z]{2})" },
    })
    await act(async () => {
      rejectSave(invalidRegexResponse())
      await settledSave
    })

    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.getByTestId("policy-regex-pattern")).toHaveValue("(?P<code>[A-Z]{2})")
  })

  it("ignores a delayed regex error after closing and reopening another policy", async () => {
    let rejectSave!: (reason: unknown) => void
    let settledSave!: Promise<void>
    const onSave = vi.fn((_payload: PolicyCreatePayload) => {
      const pendingSave = new Promise<void>((_resolve, reject) => {
        rejectSave = reject
      })
      settledSave = pendingSave.catch(() => undefined)
      return pendingSave
    })
    const firstPolicy = makePolicy()
    const replacementPolicy = makePolicy({
      id: "synthetic-replacement-policy",
      name: "Replacement rule",
      rule_type: "keyword",
      parameters: { keyword: "synthetic" },
    })
    const onClose = vi.fn()

    const { rerender } = render(
      <PolicyBuilderModal
        mode="edit"
        policy={firstPolicy}
        isOpen={true}
        isSaving={false}
        onClose={onClose}
        onSave={onSave}
      />,
    )
    fireEvent.click(screen.getByTestId("policy-save-button"))
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce())

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(onClose).toHaveBeenCalledOnce()
    rerender(
      <PolicyBuilderModal
        mode="edit"
        policy={firstPolicy}
        isOpen={false}
        isSaving={false}
        onClose={onClose}
        onSave={onSave}
      />,
    )
    rerender(
      <PolicyBuilderModal
        mode="edit"
        policy={replacementPolicy}
        isOpen={true}
        isSaving={false}
        onClose={onClose}
        onSave={onSave}
      />,
    )
    await waitFor(() => expect(screen.getByLabelText("Name")).toHaveValue("Replacement rule"))

    await act(async () => {
      rejectSave(invalidRegexResponse())
      await settledSave
    })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.getByLabelText("Name")).toHaveValue("Replacement rule")
  })
})
