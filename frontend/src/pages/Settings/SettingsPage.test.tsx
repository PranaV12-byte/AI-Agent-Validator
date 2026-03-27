import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
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
})
