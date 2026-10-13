import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useRef, useState } from "react"
import { afterEach, describe, expect, it } from "vitest"

import type { Policy } from "../../../types/api"
import DeleteConfirmationModal from "./DeleteConfirmationModal"

afterEach(cleanup)

const policy: Policy = {
  id: "synthetic-policy",
  tenant_id: "synthetic-tenant",
  name: "Synthetic policy",
  description: null,
  rule_text: "Protect a synthetic test case",
  rule_type: "keyword",
  parameters: { keyword: "synthetic" },
  is_enabled: true,
  version: 1,
  policy_hash: null,
  algorand_tx_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}

function DeleteHarness() {
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null)
  const [hasPolicy, setHasPolicy] = useState(true)
  const fallbackFocusRef = useRef<HTMLButtonElement>(null)

  return (
    <>
      <button ref={fallbackFocusRef} type="button">Add a Rule</button>
      {hasPolicy ? (
        <button type="button" onClick={() => setSelectedPolicy(policy)}>
          Delete Synthetic policy
        </button>
      ) : null}
      <DeleteConfirmationModal
        policy={selectedPolicy}
        isDeleting={false}
        onCancel={() => setSelectedPolicy(null)}
        onConfirm={async () => {
          setHasPolicy(false)
          setSelectedPolicy(null)
        }}
        fallbackFocusRef={fallbackFocusRef}
      />
    </>
  )
}

describe("DeleteConfirmationModal", () => {
  it("uses a native full-overlay dialog, focuses Cancel, and returns focus after Escape", async () => {
    const user = userEvent.setup()
    render(<DeleteHarness />)

    const opener = screen.getByRole("button", { name: "Delete Synthetic policy" })
    await user.click(opener)

    const dialog = screen.getByRole("dialog", { name: "Delete Policy" })
    expect(dialog).toHaveClass("fixed", "inset-0", "h-full", "w-full", "backdrop:bg-black/50")
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus()

    fireEvent(dialog, new Event("cancel", { cancelable: true }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(dialog).not.toHaveAttribute("open")
    expect(opener).toHaveFocus()
  })

  it("restores focus to Add a Rule when confirming removes the opener", async () => {
    const user = userEvent.setup()
    render(<DeleteHarness />)

    await user.click(screen.getByRole("button", { name: "Delete Synthetic policy" }))
    await user.click(screen.getByRole("button", { name: "Delete", exact: true }))

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.getByRole("button", { name: "Add a Rule" })).toHaveFocus()
    expect(screen.queryByRole("button", { name: "Delete Synthetic policy" })).not.toBeInTheDocument()
  })
})
