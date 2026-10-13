import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import PublicRoute from "./PublicRoute"
import * as useAuthModule from "../../hooks/useAuth"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function mockAuth(overrides: Partial<ReturnType<typeof useAuthModule.useAuth>>) {
  vi.spyOn(useAuthModule, "useAuth").mockReturnValue({
    isAuthenticated: false,
    isHydrated: true,
    isLoading: false,
    accessToken: null,
    user: null,
    login: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
    ...overrides,
  })
}

function renderPublicRoute() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route
          path="/login"
          element={
            <PublicRoute>
              <p data-testid="public-content">Login form</p>
            </PublicRoute>
          }
        />
        <Route path="/dashboard" element={<p data-testid="dashboard-page">Dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("PublicRoute", () => {
  it("renders children when user is not authenticated", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: false })
    renderPublicRoute()

    expect(screen.getByTestId("public-content")).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard-page")).not.toBeInTheDocument()
  })

  it("redirects to /dashboard when user is already authenticated", () => {
    mockAuth({ isAuthenticated: true, isHydrated: true, isLoading: false })
    renderPublicRoute()

    expect(screen.getByTestId("dashboard-page")).toBeInTheDocument()
    expect(screen.queryByTestId("public-content")).not.toBeInTheDocument()
  })

  it("shows 'Restoring session...' when not yet hydrated", () => {
    mockAuth({ isAuthenticated: false, isHydrated: false, isLoading: false })
    renderPublicRoute()

    expect(screen.getByText(/restoring session/i)).toBeInTheDocument()
    expect(screen.queryByTestId("public-content")).not.toBeInTheDocument()
    expect(screen.queryByTestId("dashboard-page")).not.toBeInTheDocument()
  })

  it("keeps the public form mounted while a token-free login request is loading", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: true, accessToken: null })
    renderPublicRoute()

    expect(screen.getByTestId("public-content")).toBeInTheDocument()
  })

  it("gates public content while an existing token is being restored", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: true, accessToken: "pending-token" })
    renderPublicRoute()

    expect(screen.getByText(/restoring session/i)).toBeInTheDocument()
    expect(screen.queryByTestId("public-content")).not.toBeInTheDocument()
  })

  it("does not redirect authenticated user until hydration is complete", () => {
    // Authenticated but not yet hydrated → show loading, not redirect
    mockAuth({ isAuthenticated: true, isHydrated: false, isLoading: false })
    renderPublicRoute()

    expect(screen.getByText(/restoring session/i)).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard-page")).not.toBeInTheDocument()
  })
})
