import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AuthProvider } from "./AuthContext"
import { useAuth } from "../hooks/useAuth"
import { apiClient } from "../services/apiClient"
import { server } from "../mocks/server"
import { makeMockJwt } from "../test/utils/mockJwt"

afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.restoreAllMocks()
})

function Probe() {
  const { login, logout, user } = useAuth()
  const [requestState, setRequestState] = useState("idle")

  function startOldRequestAndReplaceSession() {
    setRequestState("pending")
    const oldRequest = apiClient.get("/protected-resource")
    logout()
    void login({ email: "b@example.test", password: "password" })
    void oldRequest.then(
      () => setRequestState("resolved"),
      () => setRequestState("rejected"),
    )
  }

  return (
    <div>
      <p data-testid="user-email">{user?.email ?? "none"}</p>
      <p data-testid="request-state">{requestState}</p>
      <button onClick={logout}>Logout</button>
      <button onClick={() => void login({ email: "a@example.test", password: "password" })}>
        Login A
      </button>
      <button onClick={startOldRequestAndReplaceSession}>Request A then logout and login B</button>
    </div>
  )
}

function jwtWithExpiration(expiration: number, subject: string) {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value))
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub: subject, exp: expiration, jti: subject })}.synthetic`
}

describe("AuthContext session ownership with the real API client", () => {
  it("does not let a queued A request refresh or log out B", async () => {
    let protectedCalls = 0
    let refreshCalls = 0
    const protectedAuthorization: Array<string | null> = []
    const logoutAuthorizations: Array<string | null> = []
    let notifyProtectedStarted!: () => void
    const protectedStarted = new Promise<void>((resolve) => {
      notifyProtectedStarted = resolve
    })
    let releaseProtected!: () => void
    const protectedGate = new Promise<void>((resolve) => {
      releaseProtected = resolve
    })

    server.use(
      http.post("*/api/v1/auth/login", async ({ request }) => {
        const body = (await request.json()) as { email?: string }
        const isB = body.email === "b@example.test"
        return HttpResponse.json({
          access_token: isB ? "access-B" : "access-A",
          refresh_token: isB ? "refresh-B" : "refresh-A",
          token_type: "bearer",
        })
      }),
      http.post("*/api/v1/auth/logout", ({ request }) => {
        logoutAuthorizations.push(request.headers.get("authorization"))
        return HttpResponse.json({ message: "Logged out." })
      }),
      http.post("*/api/v1/auth/refresh", () => {
        refreshCalls += 1
        return HttpResponse.json({
          access_token: "access-B-refreshed",
          refresh_token: "refresh-B-refreshed",
          token_type: "bearer",
        })
      }),
      http.get("*/api/v1/auth/me", ({ request }) => {
        const isB = request.headers.get("authorization") === "Bearer access-B"
        return HttpResponse.json({
          id: isB ? "tenant-B" : "tenant-A",
          company_name: isB ? "Tenant B" : "Tenant A",
          email: isB ? "b@example.test" : "a@example.test",
          api_key_prefix: "test",
          active_policy_version: 1,
        })
      }),
      http.get("*/api/v1/protected-resource", async ({ request }) => {
        protectedCalls += 1
        protectedAuthorization.push(request.headers.get("authorization"))
        notifyProtectedStarted()
        await protectedGate
        return HttpResponse.json({ detail: "Session A expired." }, { status: 401 })
      }),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(screen.getByTestId("user-email")).toHaveTextContent("a@example.test"))

    // All three actions run in one event stack, before Axios's queued request
    // interceptor and the logout microtask can clear the old token.
    fireEvent.click(screen.getByRole("button", { name: "Request A then logout and login B" }))

    await protectedStarted
    await waitFor(() => expect(screen.getByTestId("user-email")).toHaveTextContent("b@example.test"))
    expect(protectedCalls).toBe(1)
    expect(protectedAuthorization).toEqual(["Bearer access-A"])
    expect(refreshCalls).toBe(0)

    await act(async () => {
      releaseProtected()
    })
    await waitFor(() => expect(screen.getByTestId("request-state")).toHaveTextContent("rejected"))

    expect(protectedCalls).toBe(1)
    expect(refreshCalls).toBe(0)
    expect(screen.getByTestId("user-email")).toHaveTextContent("b@example.test")
    expect(JSON.parse(localStorage.getItem("safebot.auth.session") ?? "{}").accessToken).toBe("access-B")
    expect(logoutAuthorizations.length).toBeGreaterThanOrEqual(1)
    expect(logoutAuthorizations.every((authorization) => authorization === "Bearer access-A")).toBe(true)
  })

  it("sends the restored access token when logging out an access-only legacy session", async () => {
    const legacyAccessToken = makeMockJwt("legacy-tenant")
    const logoutAuthorizations: Array<string | null> = []
    server.use(
      http.get("*/api/v1/auth/me", () =>
        HttpResponse.json({
          id: "legacy-tenant",
          company_name: "Legacy Tenant",
          email: "legacy@example.test",
          api_key_prefix: "legacy",
          active_policy_version: 1,
        }),
      ),
      http.post("*/api/v1/auth/logout", ({ request }) => {
        logoutAuthorizations.push(request.headers.get("authorization"))
        return request.headers.get("authorization") === `Bearer ${legacyAccessToken}`
          ? HttpResponse.json({ message: "Logged out." })
          : HttpResponse.json({ detail: "Invalid or expired token." }, { status: 401 })
      }),
    )
    localStorage.setItem(
      "safebot.auth.session",
      JSON.stringify({ accessToken: legacyAccessToken, refreshToken: null }),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId("user-email")).toHaveTextContent("legacy@example.test"))
    fireEvent.click(screen.getByRole("button", { name: "Logout" }))

    await waitFor(() => expect(logoutAuthorizations).toEqual([`Bearer ${legacyAccessToken}`]))
    expect(localStorage.getItem("safebot.auth.session")).toBeNull()
  })

  it("does not let a near-expiry outgoing token invalidate an incoming login", async () => {
    const accessTokenExpiration = Math.floor(Date.now() / 1000) + 600
    const accessTokenA = jwtWithExpiration(accessTokenExpiration, "tenant-A")
    let refreshCalls = 0
    const logoutAuthorizations: Array<string | null> = []
    server.use(
      http.post("*/api/v1/auth/login", async ({ request }) => {
        const body = (await request.json()) as { email?: string }
        const isB = body.email === "b@example.test"
        return HttpResponse.json({
          access_token: isB ? "access-B" : accessTokenA,
          refresh_token: isB ? "refresh-B" : "refresh-A",
          token_type: "bearer",
        })
      }),
      http.post("*/api/v1/auth/logout", ({ request }) => {
        logoutAuthorizations.push(request.headers.get("authorization"))
        return HttpResponse.json({ message: "Logged out." })
      }),
      http.post("*/api/v1/auth/refresh", () => {
        refreshCalls += 1
        return HttpResponse.json({
          access_token: "access-A-refreshed",
          refresh_token: "refresh-A-refreshed",
          token_type: "bearer",
        })
      }),
      http.get("*/api/v1/auth/me", ({ request }) => {
        const isB = request.headers.get("authorization") === "Bearer access-B"
        return HttpResponse.json({
          id: isB ? "tenant-B" : "tenant-A",
          company_name: isB ? "Tenant B" : "Tenant A",
          email: isB ? "b@example.test" : "a@example.test",
          api_key_prefix: "test",
          active_policy_version: 1,
        })
      }),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    fireEvent.click(screen.getByRole("button", { name: "Login A" }))
    await waitFor(() => expect(screen.getByTestId("user-email")).toHaveTextContent("a@example.test"))

    // Make the already-restored A access token fall within the proactive
    // refresh window only for the queued request that follows.
    const dateNow = vi.spyOn(Date, "now").mockReturnValue((accessTokenExpiration - 30) * 1000)
    fireEvent.click(screen.getByRole("button", { name: "Request A then logout and login B" }))
    await waitFor(() => expect(screen.getByTestId("request-state")).toHaveTextContent("rejected"))
    dateNow.mockRestore()

    await waitFor(() => expect(screen.getByTestId("user-email")).toHaveTextContent("b@example.test"))
    expect(refreshCalls).toBe(0)
    expect(logoutAuthorizations).toHaveLength(2)
    expect(logoutAuthorizations.every((authorization) => authorization === `Bearer ${accessTokenA}`)).toBe(true)
    expect(JSON.parse(localStorage.getItem("safebot.auth.session") ?? "{}").accessToken).toBe("access-B")
  })
})
