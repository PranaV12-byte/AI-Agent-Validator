import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { Toaster } from "sonner"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useAuth } from "../../hooks/useAuth"
import { updateProfileRequest } from "../../services/authService"
import AccountPage from "./AccountPage"

vi.mock("../../hooks/useAuth", () => ({ useAuth: vi.fn() }))
vi.mock("../../services/authService", () => ({ updateProfileRequest: vi.fn() }))

afterEach(() => cleanup())

describe("AccountPage", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok",
      user: {
        id: "t1",
        company_name: "Old Corp",
        email: "old@test.com",
        api_key_prefix: "abc",
        active_policy_version: 0,
      },
      login: vi.fn(),
      refreshProfile: vi.fn().mockResolvedValue(undefined),
      logout: vi.fn(),
    })
    vi.mocked(updateProfileRequest).mockResolvedValue({
      id: "t1",
      company_name: "New Corp",
      email: "old@test.com",
      api_key_prefix: "abc",
      active_policy_version: 0,
    })
  })

  it("shows pre-filled company name", () => {
    render(<AccountPage />)
    expect(screen.getByDisplayValue("Old Corp")).toBeInTheDocument()
  })

  it("saves company name on submit", async () => {
    render(
      <>
        <Toaster />
        <AccountPage />
      </>,
    )
    fireEvent.change(screen.getByDisplayValue("Old Corp"), {
      target: { value: "New Corp" },
    })
    fireEvent.click(screen.getByRole("button", { name: /^Save$/i }))
    await waitFor(() =>
      expect(updateProfileRequest).toHaveBeenCalledWith({ company_name: "New Corp" }),
    )
    expect(await screen.findByText("Company name updated")).toBeInTheDocument()
  })

  it("shows re-verification warning for email changes", () => {
    render(<AccountPage />)
    expect(
      screen.getByText(/Changing your email will require re-verification/i),
    ).toBeInTheDocument()
  })
})
