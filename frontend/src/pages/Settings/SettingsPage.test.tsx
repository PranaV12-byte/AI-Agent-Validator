import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { Toaster } from "sonner"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import SettingsPage from "./SettingsPage"
import { useAuth } from "../../hooks/useAuth"
import { regenerateApiKeyRequest } from "../../services/authService"
import { fetchSafetyConfig, updateSafetyConfig } from "../../services/dashboardService"

vi.mock("../../hooks/useAuth", () => ({
  useAuth: vi.fn(),
}))

vi.mock("../../services/authService", () => ({
  regenerateApiKeyRequest: vi.fn(),
}))

vi.mock("../../services/dashboardService", () => ({
  fetchSafetyConfig: vi.fn(),
  updateSafetyConfig: vi.fn(),
}))

afterEach(() => {
  cleanup()
})

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "token",
      user: {
        id: "tenant-123",
        company_name: "Test Co",
        email: "test@example.com",
        api_key_prefix: "abc12345",
        active_policy_version: 1,
      },
      login: vi.fn(),
      refreshProfile: vi.fn().mockResolvedValue(undefined),
      logout: vi.fn(),
    })

    vi.mocked(fetchSafetyConfig).mockResolvedValue({
      id: "cfg-1",
      tenant_id: "tenant-123",
      global_block_enabled: false,
      injection_protection: true,
      injection_sensitivity: "moderate",
      pii_redaction: true,
      pii_types: ["email"],
      policy_enforcement: true,
      fail_mode: "closed",
      fallback_message: "blocked",
      log_retention_days: 30,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })

    vi.mocked(regenerateApiKeyRequest).mockResolvedValue({
      api_key: "new-key",
      api_key_prefix: "newkey12",
    })

    vi.mocked(updateSafetyConfig).mockResolvedValue({
      id: "cfg-1",
      tenant_id: "tenant-123",
      global_block_enabled: true,
      injection_protection: true,
      injection_sensitivity: "moderate",
      pii_redaction: true,
      pii_types: ["email"],
      policy_enforcement: true,
      fail_mode: "closed",
      fallback_message: "blocked",
      log_retention_days: 30,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })

    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    })
  })

  it("activates save button when settings are modified", async () => {
    render(<SettingsPage />)

    const saveButton = await screen.findByTestId("settings-save-button")
    expect(saveButton).toBeDisabled()

    fireEvent.click(screen.getByLabelText("Block all harmful messages"))

    expect(saveButton).toBeEnabled()
    expect(saveButton).toHaveTextContent("Save Unsaved Changes")
  })

  it("copies API key prefix to clipboard", async () => {
    render(<SettingsPage />)

    await waitFor(() => {
      expect(fetchSafetyConfig).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByText("Copy Prefix"))

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("abc12345")
  })

  it("shows success toast after settings are saved", async () => {
    render(
      <>
        <Toaster />
        <SettingsPage />
      </>,
    )

    // Wait for config to load
    const saveButton = await screen.findByTestId("settings-save-button")
    expect(saveButton).toBeDisabled()

    // Make a change to enable the save button
    fireEvent.click(screen.getByLabelText("Block all harmful messages"))
    expect(saveButton).toBeEnabled()

    fireEvent.click(saveButton)

    expect(await screen.findByText("Settings saved")).toBeInTheDocument()
  })

  it("requires two clicks to rotate the API key (confirmation step)", async () => {
    render(<SettingsPage />)

    // First click: should show confirmation, NOT call rotate
    const rotateBtn = await screen.findByRole("button", { name: /Regenerate API Key/i })
    fireEvent.click(rotateBtn)

    expect(regenerateApiKeyRequest).not.toHaveBeenCalled()
    expect(await screen.findByText(/This will break existing integrations/i)).toBeInTheDocument()

    // Cancel returns to default state
    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }))
    expect(screen.queryByText(/This will break existing integrations/i)).not.toBeInTheDocument()
  })

  it("rotates key when user confirms", async () => {
    render(<SettingsPage />)

    const rotateBtn = await screen.findByRole("button", { name: /Regenerate API Key/i })
    fireEvent.click(rotateBtn)
    fireEvent.click(await screen.findByRole("button", { name: /Yes, rotate key/i }))

    await waitFor(() => expect(regenerateApiKeyRequest).toHaveBeenCalledOnce())
  })

  it("shows error message when save fails", async () => {
    vi.mocked(updateSafetyConfig).mockRejectedValue(new Error("Server error"))

    render(<SettingsPage />)

    const saveButton = await screen.findByTestId("settings-save-button")

    // Make a change to enable the save button
    fireEvent.click(screen.getByLabelText("Block all harmful messages"))
    fireEvent.click(saveButton)

    expect(
      await screen.findByText("Could not save settings. Please try again."),
    ).toBeInTheDocument()
  })
})
