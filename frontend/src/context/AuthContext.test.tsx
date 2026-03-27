import { AxiosError } from "axios"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi, beforeEach } from "vitest"

import { AuthProvider } from "./AuthContext"
import { useAuth } from "../hooks/useAuth"
import { fetchTenantProfile, loginRequest } from "../services/authService"
import * as apiClientModule from "../services/apiClient"

vi.mock("../services/authService", () => ({
  fetchTenantProfile: vi.fn(),
  loginRequest: vi.fn(),
  logoutRequest: vi.fn().mockResolvedValue(undefined),
}))

function Probe() {
  const { isAuthenticated, isLoading, user } = useAuth()
  return (
    <div>
      <p data-testid="auth-state">{isAuthenticated ? "in" : "out"}</p>
      <p data-testid="loading-state">{isLoading ? "loading" : "idle"}</p>
      <p data-testid="user-state">{user ? user.email : "none"}</p>
    </div>
  )
}

function Wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

describe("AuthContext", () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.mocked(loginRequest).mockReset()
    vi.mocked(fetchTenantProfile).mockReset()
    localStorage.clear()
  })

  it("logs out and clears localStorage when /auth/me returns 401", async () => {
    localStorage.setItem("safebot.auth.session", JSON.stringify({ accessToken: "expired" }))

    const unauthorized = new AxiosError(
      "Unauthorized",
      "ERR_BAD_REQUEST",
      undefined,
      undefined,
      {
        status: 401,
        statusText: "Unauthorized",
        headers: {} as any,
        config: { headers: {} as any },
        data: { detail: "Invalid or expired token" },
      },
    )

    vi.mocked(fetchTenantProfile).mockRejectedValue(unauthorized)

    render(<Probe />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(localStorage.getItem("safebot.auth.session")).toBeNull()
    })

    expect(screen.getByTestId("auth-state")).toHaveTextContent("out")
    expect(screen.getByTestId("loading-state")).toHaveTextContent("idle")
    expect(screen.getByTestId("user-state")).toHaveTextContent("none")
  })

  it("registers unauthorized handler during provider lifecycle", async () => {
    const spy = vi.spyOn(apiClientModule, "registerUnauthorizedHandler")

    const { unmount } = render(<Probe />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(spy).toHaveBeenCalled()
    })

    unmount()

    expect(spy).toHaveBeenLastCalledWith(null)
    spy.mockRestore()
  })
})
