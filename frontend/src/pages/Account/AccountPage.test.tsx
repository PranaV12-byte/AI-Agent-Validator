import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { Toaster } from "sonner"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useAuth } from "../../hooks/useAuth"
import { updateProfileRequest } from "../../services/authService"
import AccountPage from "./AccountPage"

vi.mock("../../hooks/useAuth", () => ({ useAuth: vi.fn() }))
vi.mock("../../services/authService", () => ({ updateProfileRequest: vi.fn() }))

afterEach(() => cleanup())

const refreshProfileMock = vi.fn()
const logoutMock = vi.fn()

function LocationProbe() {
  const location = useLocation()
  return <p data-testid="destination">{`${location.pathname}${location.search}`}</p>
}

function renderAccountPage() {
  return render(
    <MemoryRouter initialEntries={["/account"]}>
      <Routes>
        <Route path="/account" element={<AccountPage />} />
        <Route path="/verify-email" element={<LocationProbe />} />
        <Route path="/login" element={<LocationProbe />} />
      </Routes>
      <Toaster />
    </MemoryRouter>,
  )
}

describe("AccountPage", () => {
  beforeEach(() => {
    refreshProfileMock.mockReset()
    logoutMock.mockReset()
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
      refreshProfile: refreshProfileMock.mockResolvedValue(undefined),
      logout: logoutMock,
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
    renderAccountPage()
    expect(screen.getByDisplayValue("Old Corp")).toBeInTheDocument()
  })

  it("saves company name on submit", async () => {
    renderAccountPage()
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
    renderAccountPage()
    expect(
      screen.getByText(/Changing your email will require re-verification/i),
    ).toBeInTheDocument()
  })

  it("hands a local verification link off before logging out without refreshing the revoked profile", async () => {
    vi.mocked(updateProfileRequest).mockResolvedValueOnce({
      id: "t1",
      company_name: "Old Corp",
      email: "new@example.test",
      api_key_prefix: "abc",
      active_policy_version: 0,
      verification_url: "http://localhost:5173/verify-email?token=local-token",
    })
    renderAccountPage()

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "new@example.test" },
    })
    fireEvent.click(screen.getByRole("button", { name: /update email/i }))

    await waitFor(() => {
      expect(screen.getByTestId("destination")).toHaveTextContent(
        "/verify-email?token=local-token",
      )
    })
    expect(updateProfileRequest).toHaveBeenCalledWith({ email: "new@example.test" })
    expect(logoutMock).toHaveBeenCalledOnce()
    expect(refreshProfileMock).not.toHaveBeenCalled()
  })

  it("routes to a generic verify-first sign-in message when no local URL is returned", async () => {
    vi.mocked(updateProfileRequest).mockResolvedValueOnce({
      id: "t1",
      company_name: "Old Corp",
      email: "new@example.test",
      api_key_prefix: "abc",
      active_policy_version: 0,
      verification_url: null,
    })
    renderAccountPage()

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "new@example.test" },
    })
    fireEvent.click(screen.getByRole("button", { name: /update email/i }))

    await waitFor(() => {
      expect(screen.getByTestId("destination")).toHaveTextContent("/login?verification=pending")
    })
    expect(logoutMock).toHaveBeenCalledOnce()
    expect(refreshProfileMock).not.toHaveBeenCalled()
  })
})
