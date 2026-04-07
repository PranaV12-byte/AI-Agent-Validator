import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import PolicyList from "./PolicyList"
import type { Policy } from "../../../types/api"

afterEach(cleanup)

function makePolicy(overrides: Partial<Policy> = {}): Policy {
  return {
    id: "policy-1",
    tenant_id: "tenant-1",
    name: "Block Injections",
    description: "Stops prompt injection attacks",
    rule_text: "Ignore all previous instructions",
    rule_type: "prompt_injection",
    parameters: {},
    is_enabled: true,
    version: 1,
    policy_hash: null,
    algorand_tx_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

const defaultListProps = {
  policies: [],
  isLoading: false,
  error: null,
  onCreate: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  onToggle: vi.fn(),
}

describe("PolicyList", () => {
  it("renders 'No rules set up yet' when policies list is empty", () => {
    render(<PolicyList {...defaultListProps} />)
    expect(screen.getByText(/no rules set up yet/i)).toBeInTheDocument()
  })

  it("renders 'Add Your First Rule' button in empty state", () => {
    render(<PolicyList {...defaultListProps} />)
    expect(screen.getByRole("button", { name: /add your first rule/i })).toBeInTheDocument()
  })

  it("calls onCreate when 'Add Your First Rule' is clicked in empty state", async () => {
    const user = userEvent.setup()
    const onCreate = vi.fn()
    render(<PolicyList {...defaultListProps} onCreate={onCreate} />)

    await user.click(screen.getByRole("button", { name: /add your first rule/i }))
    expect(onCreate).toHaveBeenCalledOnce()
  })

  it("renders 'Add a Rule' button in header area", () => {
    render(<PolicyList {...defaultListProps} />)
    expect(screen.getByRole("button", { name: /add a rule/i })).toBeInTheDocument()
  })

  it("renders policy card with name when policies are present", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy({ name: "My Keyword Policy" })]}
      />,
    )
    expect(screen.getByText("My Keyword Policy")).toBeInTheDocument()
  })

  it("renders formatted rule_type label for keyword type", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy({ rule_type: "keyword" })]}
      />,
    )
    expect(screen.getByText(/word match/i)).toBeInTheDocument()
  })

  it("renders formatted rule_type label for prompt_injection type", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy({ rule_type: "prompt_injection" })]}
      />,
    )
    expect(screen.getByText(/block manipulation/i)).toBeInTheDocument()
  })

  it("renders Edit and Delete buttons for each policy", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy()]}
      />,
    )
    expect(screen.getByRole("button", { name: /edit/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /delete/i })).toBeInTheDocument()
  })

  it("calls onEdit with the policy object when Edit is clicked", async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    const policy = makePolicy({ name: "Test Policy" })
    render(<PolicyList {...defaultListProps} policies={[policy]} onEdit={onEdit} />)

    await user.click(screen.getByRole("button", { name: /edit/i }))
    expect(onEdit).toHaveBeenCalledWith(policy)
  })

  it("calls onDelete with the policy object when Delete is clicked", async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    const policy = makePolicy({ id: "del-policy-1" })
    render(<PolicyList {...defaultListProps} policies={[policy]} onDelete={onDelete} />)

    await user.click(screen.getByRole("button", { name: /delete/i }))
    expect(onDelete).toHaveBeenCalledWith(policy)
  })

  it("calls onToggle with the policy when toggle checkbox is clicked", async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    const policy = makePolicy({ is_enabled: true })
    render(<PolicyList {...defaultListProps} policies={[policy]} onToggle={onToggle} />)

    // The toggle is a visually hidden checkbox in a label
    const toggleCheckbox = screen.getByRole("checkbox")
    await user.click(toggleCheckbox)
    expect(onToggle).toHaveBeenCalledWith(policy)
  })

  it("renders toggle checkbox as checked when policy is enabled", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy({ is_enabled: true })]}
      />,
    )
    expect(screen.getByRole("checkbox")).toBeChecked()
  })

  it("renders toggle checkbox as unchecked when policy is disabled", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy({ is_enabled: false })]}
      />,
    )
    expect(screen.getByRole("checkbox")).not.toBeChecked()
  })

  it("shows 'No description provided.' when description is empty", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[makePolicy({ description: "" })]}
      />,
    )
    expect(screen.getByText("No description provided.")).toBeInTheDocument()
  })

  it("renders multiple policy cards for multiple policies", () => {
    render(
      <PolicyList
        {...defaultListProps}
        policies={[
          makePolicy({ id: "p1", name: "Policy One" }),
          makePolicy({ id: "p2", name: "Policy Two" }),
          makePolicy({ id: "p3", name: "Policy Three" }),
        ]}
      />,
    )
    expect(screen.getByText("Policy One")).toBeInTheDocument()
    expect(screen.getByText("Policy Two")).toBeInTheDocument()
    expect(screen.getByText("Policy Three")).toBeInTheDocument()
  })

  it("renders error message when error prop is set", () => {
    render(<PolicyList {...defaultListProps} error="Failed to load policies" />)
    expect(screen.getByText(/unable to load policies/i)).toBeInTheDocument()
  })

  it("renders skeleton loaders when isLoading=true", () => {
    render(<PolicyList {...defaultListProps} isLoading={true} />)
    // Skeleton divs have animate-pulse class
    const skeletons = document.querySelectorAll(".animate-pulse")
    expect(skeletons.length).toBeGreaterThan(0)
  })
})
