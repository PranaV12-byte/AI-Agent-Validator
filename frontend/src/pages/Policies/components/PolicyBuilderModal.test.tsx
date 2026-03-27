import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

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
})
