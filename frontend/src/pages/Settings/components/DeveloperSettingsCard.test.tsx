import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import DeveloperSettingsCard from "./DeveloperSettingsCard"

afterEach(cleanup)

const defaultProps = {
  tenantId: "tenant-abc-123",
  apiKeyPrefix: "sk_live_",
  newApiKey: null,
  isRotating: false,
  onRotate: vi.fn().mockResolvedValue(undefined),
  onCopyPrefix: vi.fn().mockResolvedValue(undefined),
  onCopyNewKey: vi.fn().mockResolvedValue(undefined),
}

describe("DeveloperSettingsCard", () => {
  it("renders tenant ID", () => {
    render(<DeveloperSettingsCard {...defaultProps} />)
    expect(screen.getByText("tenant-abc-123")).toBeInTheDocument()
  })

  it("renders API key prefix", () => {
    render(<DeveloperSettingsCard {...defaultProps} />)
    expect(screen.getByText("sk_live_")).toBeInTheDocument()
  })

  it("renders the 'Regenerate API Key' button", () => {
    render(<DeveloperSettingsCard {...defaultProps} />)
    expect(screen.getByRole("button", { name: /regenerate api key/i })).toBeInTheDocument()
  })

  it("shows 'Rotating...' text and disables button when isRotating=true", () => {
    render(<DeveloperSettingsCard {...defaultProps} isRotating={true} />)
    const btn = screen.getByRole("button", { name: /rotating/i })
    expect(btn).toBeDisabled()
  })

  it("enables the regenerate button when isRotating=false", () => {
    render(<DeveloperSettingsCard {...defaultProps} isRotating={false} />)
    expect(screen.getByRole("button", { name: /regenerate api key/i })).not.toBeDisabled()
  })

  it("calls onRotate after confirming the rotation dialog", async () => {
    const user = userEvent.setup()
    const onRotate = vi.fn().mockResolvedValue(undefined)
    render(<DeveloperSettingsCard {...defaultProps} onRotate={onRotate} />)

    await user.click(screen.getByRole("button", { name: /regenerate api key/i }))
    expect(onRotate).not.toHaveBeenCalled()
    await user.click(screen.getByRole("button", { name: /yes, rotate key/i }))
    expect(onRotate).toHaveBeenCalledOnce()
  })

  it("calls onCopyPrefix when Copy Prefix button is clicked", async () => {
    const user = userEvent.setup()
    const onCopyPrefix = vi.fn().mockResolvedValue(undefined)
    render(<DeveloperSettingsCard {...defaultProps} onCopyPrefix={onCopyPrefix} />)

    await user.click(screen.getByRole("button", { name: /copy prefix/i }))
    expect(onCopyPrefix).toHaveBeenCalledOnce()
  })

  it("does not render new API key section when newApiKey is null", () => {
    render(<DeveloperSettingsCard {...defaultProps} newApiKey={null} />)
    expect(screen.queryByText(/copy now/i)).not.toBeInTheDocument()
  })

  it("renders masked new API key when newApiKey is provided", () => {
    const newKey = "abcd1234efgh5678ijkl9012mnop3456"
    render(<DeveloperSettingsCard {...defaultProps} newApiKey={newKey} />)
    // Shows first 8 chars + 24 asterisks
    expect(screen.getByText("abcd1234" + "*".repeat(24))).toBeInTheDocument()
  })

  it("reveals full key when Reveal button is clicked", async () => {
    const user = userEvent.setup()
    const newKey = "abcd1234efgh5678ijkl9012mnop3456"
    render(<DeveloperSettingsCard {...defaultProps} newApiKey={newKey} />)

    await user.click(screen.getByRole("button", { name: /reveal/i }))
    expect(screen.getByText(newKey)).toBeInTheDocument()
  })

  it("hides full key when Hide button is clicked after revealing", async () => {
    const user = userEvent.setup()
    const newKey = "abcd1234efgh5678ijkl9012mnop3456"
    render(<DeveloperSettingsCard {...defaultProps} newApiKey={newKey} />)

    await user.click(screen.getByRole("button", { name: /reveal/i }))
    expect(screen.getByText(newKey)).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /hide/i }))
    expect(screen.queryByText(newKey)).not.toBeInTheDocument()
    expect(screen.getByText("abcd1234" + "*".repeat(24))).toBeInTheDocument()
  })

  it("calls onCopyNewKey when Copy key button is clicked", async () => {
    const user = userEvent.setup()
    const onCopyNewKey = vi.fn().mockResolvedValue(undefined)
    const newKey = "abcd1234efgh5678ijkl9012mnop3456"
    render(<DeveloperSettingsCard {...defaultProps} newApiKey={newKey} onCopyNewKey={onCopyNewKey} />)

    await user.click(screen.getByRole("button", { name: /copy key/i }))
    expect(onCopyNewKey).toHaveBeenCalledOnce()
  })

  it("resets to masked view when a new key arrives (showKey resets)", async () => {
    const user = userEvent.setup()
    const key1 = "firstkey" + "x".repeat(24)
    const key2 = "secondke" + "y".repeat(24)
    const { rerender } = render(<DeveloperSettingsCard {...defaultProps} newApiKey={key1} />)

    // Reveal the first key
    await user.click(screen.getByRole("button", { name: /reveal/i }))
    expect(screen.getByText(key1)).toBeInTheDocument()

    // Simulate new key arriving (key rotation happened again)
    rerender(<DeveloperSettingsCard {...defaultProps} newApiKey={key2} />)

    // showKey should reset to false — masked view shown
    expect(screen.queryByText(key2)).not.toBeInTheDocument()
    expect(screen.getByText("secondke" + "*".repeat(24))).toBeInTheDocument()
  })

  it("displays '--' for tenantId when null", () => {
    render(<DeveloperSettingsCard {...defaultProps} tenantId={null} />)
    // Should show placeholder '--'
    expect(screen.getAllByText("--").length).toBeGreaterThanOrEqual(1)
  })
})
