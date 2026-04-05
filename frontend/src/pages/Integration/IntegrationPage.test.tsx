import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter, Routes, Route } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import IntegrationPage from "./IntegrationPage"
import { useAuth } from "../../hooks/useAuth"

vi.mock("../../hooks/useAuth", () => ({ useAuth: vi.fn() }))

afterEach(() => cleanup())

describe("IntegrationPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok",
      user: { id: "t1", company_name: "Co", email: "a@b.com", api_key_prefix: "abc12345", active_policy_version: 0 },
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
  })

  it("shows the full-key callout with a link to settings", () => {
    render(<MemoryRouter><IntegrationPage /></MemoryRouter>)
    expect(screen.getByText(/If you don't have it, go to/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Go to Settings/i })).toBeInTheDocument()
  })

  it("navigates to /settings when the callout button is clicked", () => {
    render(
      <MemoryRouter initialEntries={["/integration"]}>
        <Routes>
          <Route path="/integration" element={<IntegrationPage />} />
          <Route path="/settings" element={<div>settings page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByRole("button", { name: /Go to Settings/i }))
    expect(screen.getByText("settings page")).toBeInTheDocument()
  })
})
