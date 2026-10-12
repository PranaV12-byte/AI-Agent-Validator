import { AxiosError } from "axios"
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi, beforeEach } from "vitest"

import { AuthProvider } from "./AuthContext"
import { useAuth } from "../hooks/useAuth"
import {
  fetchTenantProfile,
  loginRequest,
  logoutRequest,
  refreshTokenRequest,
} from "../services/authService"
import * as apiClientModule from "../services/apiClient"
import type { AuthResponse, TenantProfile } from "../types/api"

vi.mock("../services/authService", () => ({
  fetchTenantProfile: vi.fn(),
  loginRequest: vi.fn(),
  logoutRequest: vi.fn().mockResolvedValue(undefined),
  refreshTokenRequest: vi.fn(),
}))

function Probe() {
  const { isAuthenticated, isLoading, user, login, logout } = useAuth()
  return (
    <div>
      <p data-testid="auth-state">{isAuthenticated ? "in" : "out"}</p>
      <p data-testid="loading-state">{isLoading ? "loading" : "idle"}</p>
      <p data-testid="user-state">{user ? user.email : "none"}</p>
      <button onClick={() => void login({ email: "a@example.test", password: "password" })}>
        Login A
      </button>
      <button onClick={() => void login({ email: "b@example.test", password: "password" })}>
        Login B
      </button>
      <button onClick={logout}>Logout</button>
    </div>
  )
}

function Wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function authResponse(accessToken: string, refreshToken: string) {
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    token_type: "bearer",
  }
}

function profile(email: string): TenantProfile {
  return {
    id: email,
    company_name: email,
    email,
    api_key_prefix: "test",
    active_policy_version: 1,
  }
}

describe("AuthContext", () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    vi.mocked(loginRequest).mockReset()
    vi.mocked(fetchTenantProfile).mockReset()
    vi.mocked(logoutRequest).mockClear()
    vi.mocked(refreshTokenRequest).mockReset()
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

  it("does not let an old profile success overwrite or clear the new session loading state", async () => {
    const profileA = deferred<TenantProfile>()
    const profileB = deferred<TenantProfile>()
    vi.mocked(loginRequest)
      .mockResolvedValueOnce(authResponse("access-A", "refresh-A"))
      .mockResolvedValueOnce(authResponse("access-B", "refresh-B"))
    vi.mocked(fetchTenantProfile)
      .mockReturnValueOnce(profileA.promise)
      .mockReturnValueOnce(profileB.promise)

    render(<Probe />, { wrapper: Wrapper })
    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole("button", { name: "Login B" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(2))
    expect(screen.getByTestId("loading-state")).toHaveTextContent("loading")

    await act(async () => {
      profileA.resolve(profile("a@example.test"))
      await profileA.promise
    })

    expect(screen.getByTestId("loading-state")).toHaveTextContent("loading")
    expect(screen.getByTestId("user-state")).toHaveTextContent("none")
    expect(JSON.parse(localStorage.getItem("safebot.auth.session") ?? "{}").accessToken).toBe("access-B")

    await act(async () => {
      profileB.resolve(profile("b@example.test"))
      await profileB.promise
    })

    expect(screen.getByTestId("user-state")).toHaveTextContent("b@example.test")
    expect(screen.getByTestId("auth-state")).toHaveTextContent("in")
  })

  it("does not let an old profile 401 log out a newer session", async () => {
    const profileA = deferred<TenantProfile>()
    const profileB = deferred<TenantProfile>()
    vi.mocked(loginRequest)
      .mockResolvedValueOnce(authResponse("access-A", "refresh-A"))
      .mockResolvedValueOnce(authResponse("access-B", "refresh-B"))
    vi.mocked(fetchTenantProfile)
      .mockReturnValueOnce(profileA.promise)
      .mockReturnValueOnce(profileB.promise)

    render(<Probe />, { wrapper: Wrapper })
    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole("button", { name: "Logout" }))
    fireEvent.click(screen.getByRole("button", { name: "Login B" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(2))
    const logoutCountAfterReplacement = vi.mocked(logoutRequest).mock.calls.length

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
    await act(async () => {
      profileA.reject(unauthorized)
      await profileA.promise.catch(() => undefined)
    })

    expect(screen.getByTestId("auth-state")).toHaveTextContent("out")
    expect(screen.getByTestId("loading-state")).toHaveTextContent("loading")
    expect(screen.getByTestId("user-state")).toHaveTextContent("none")
    expect(JSON.parse(localStorage.getItem("safebot.auth.session") ?? "{}").accessToken).toBe("access-B")
    expect(logoutRequest).toHaveBeenCalledTimes(logoutCountAfterReplacement)

    await act(async () => {
      profileB.resolve(profile("b@example.test"))
      await profileB.promise
    })
    expect(screen.getByTestId("user-state")).toHaveTextContent("b@example.test")
    expect(screen.getByTestId("auth-state")).toHaveTextContent("in")
  })

  it("ignores a held old-session refresh success after logout and a new login", async () => {
    const refreshResult = deferred<AuthResponse>()
    vi.mocked(loginRequest)
      .mockResolvedValueOnce(authResponse("access-A", "refresh-A"))
      .mockResolvedValueOnce(authResponse("access-B", "refresh-B"))
    vi.mocked(fetchTenantProfile)
      .mockResolvedValueOnce(profile("a@example.test"))
      .mockResolvedValueOnce(profile("b@example.test"))
    vi.mocked(refreshTokenRequest).mockReturnValueOnce(refreshResult.promise)
    const refreshRegistration = vi.spyOn(apiClientModule, "registerRefreshHandler")

    render(<Probe />, { wrapper: Wrapper })
    await waitFor(() => expect(refreshRegistration).toHaveBeenCalled())
    const refreshHandler = refreshRegistration.mock.calls
      .map(([handler]) => handler)
      .find((handler) => handler !== null)
    expect(refreshHandler).toBeDefined()

    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(1))

    let oldRefresh!: Promise<void>
    act(() => {
      oldRefresh = refreshHandler!()
    })
    await waitFor(() => expect(refreshTokenRequest).toHaveBeenCalledWith("refresh-A"))

    fireEvent.click(screen.getByRole("button", { name: "Logout" }))
    fireEvent.click(screen.getByRole("button", { name: "Login B" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(2))

    await act(async () => {
      refreshResult.resolve(authResponse("access-A-refreshed", "refresh-A-refreshed"))
      await oldRefresh
    })

    expect(JSON.parse(localStorage.getItem("safebot.auth.session") ?? "{}").accessToken).toBe("access-B")
    expect(screen.getByTestId("user-state")).toHaveTextContent("b@example.test")
    expect(screen.getByTestId("auth-state")).toHaveTextContent("in")
    refreshRegistration.mockRestore()
  })

  it("does not let a held old-session refresh failure log out a newer session", async () => {
    const refreshResult = deferred<AuthResponse>()
    vi.mocked(loginRequest)
      .mockResolvedValueOnce(authResponse("access-A", "refresh-A"))
      .mockResolvedValueOnce(authResponse("access-B", "refresh-B"))
    vi.mocked(fetchTenantProfile)
      .mockResolvedValueOnce(profile("a@example.test"))
      .mockResolvedValueOnce(profile("b@example.test"))
    vi.mocked(refreshTokenRequest).mockReturnValueOnce(refreshResult.promise)
    const refreshRegistration = vi.spyOn(apiClientModule, "registerRefreshHandler")

    render(<Probe />, { wrapper: Wrapper })
    await waitFor(() => expect(refreshRegistration).toHaveBeenCalled())
    const refreshHandler = refreshRegistration.mock.calls
      .map(([handler]) => handler)
      .find((handler) => handler !== null)
    expect(refreshHandler).toBeDefined()

    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(1))

    let oldRefresh!: Promise<void>
    act(() => {
      oldRefresh = refreshHandler!()
    })
    await waitFor(() => expect(refreshTokenRequest).toHaveBeenCalledWith("refresh-A"))

    fireEvent.click(screen.getByRole("button", { name: "Logout" }))
    fireEvent.click(screen.getByRole("button", { name: "Login B" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledTimes(2))
    const logoutCountAfterReplacement = vi.mocked(logoutRequest).mock.calls.length

    await act(async () => {
      refreshResult.reject(new Error("old refresh failed"))
      await oldRefresh
    })

    expect(JSON.parse(localStorage.getItem("safebot.auth.session") ?? "{}").accessToken).toBe("access-B")
    expect(screen.getByTestId("user-state")).toHaveTextContent("b@example.test")
    expect(screen.getByTestId("auth-state")).toHaveTextContent("in")
    expect(logoutRequest).toHaveBeenCalledTimes(logoutCountAfterReplacement)
    refreshRegistration.mockRestore()
  })

  it("does not print token-bearing request details when server-side logout fails", async () => {
    vi.mocked(loginRequest).mockResolvedValueOnce(authResponse("access-A", "refresh-A"))
    vi.mocked(fetchTenantProfile).mockResolvedValueOnce(profile("a@example.test"))
    vi.mocked(logoutRequest).mockRejectedValueOnce(
      new AxiosError(
        "Request failed",
        "ERR_BAD_REQUEST",
        {
          headers: { Authorization: "Bearer synthetic-access-secret" },
          data: { refresh_token: "synthetic-refresh-secret" },
        } as any,
      ),
    )
    const warning = vi.spyOn(console, "warn").mockImplementation(() => undefined)

    render(<Probe />, { wrapper: Wrapper })
    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(fetchTenantProfile).toHaveBeenCalledOnce())
    fireEvent.click(screen.getByRole("button", { name: "Logout" }))

    await waitFor(() => expect(warning).toHaveBeenCalledOnce())
    expect(warning.mock.calls[0]).toHaveLength(1)
    const loggedOutput = JSON.stringify(warning.mock.calls)
    expect(loggedOutput).not.toContain("synthetic-access-secret")
    expect(loggedOutput).not.toContain("synthetic-refresh-secret")
    warning.mockRestore()
  })
})
