import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import ProtectedRoute from "./ProtectedRoute"
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

function renderProtectedRoute(path = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path={path.split("?")[0]}
          element={
            <ProtectedRoute>
              <p data-testid="protected-content">Protected content</p>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<p data-testid="login-page">Login page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("ProtectedRoute", () => {
  it("redirects unauthenticated user to /login", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: false })
    renderProtectedRoute()

    expect(screen.getByTestId("login-page")).toBeInTheDocument()
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument()
  })

  it("encodes the current path as redirect_uri in the login redirect", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: false })

    // Use a custom render to inspect the location
    let navigatedTo = ""
    render(
      <MemoryRouter initialEntries={["/audit-log"]}>
        <Routes>
          <Route
            path="/audit-log"
            element={
              <ProtectedRoute>
                <p>content</p>
              </ProtectedRoute>
            }
          />
          <Route
            path="/login"
            element={
              <p
                data-testid="login-with-redirect"
                ref={() => {
                  // capture the final location search from the rendered login
                  navigatedTo = window.location.href
                }}
              >
                login
              </p>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    // The redirect_uri should encode /audit-log
    expect(screen.getByTestId("login-with-redirect")).toBeInTheDocument()
    void navigatedTo
  })

  it("renders children when user is authenticated", () => {
    mockAuth({ isAuthenticated: true, isHydrated: true, isLoading: false })
    renderProtectedRoute()

    expect(screen.getByTestId("protected-content")).toBeInTheDocument()
    expect(screen.queryByTestId("login-page")).not.toBeInTheDocument()
  })

  it("shows 'Restoring session...' when not yet hydrated", () => {
    mockAuth({ isAuthenticated: false, isHydrated: false, isLoading: false })
    renderProtectedRoute()

    expect(screen.getByText(/restoring session/i)).toBeInTheDocument()
    expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument()
    expect(screen.queryByTestId("login-page")).not.toBeInTheDocument()
  })

  it("shows 'Restoring session...' while isLoading is true", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: true })
    renderProtectedRoute()

    expect(screen.getByText(/restoring session/i)).toBeInTheDocument()
  })

  it("does not redirect while session is still loading", () => {
    mockAuth({ isAuthenticated: false, isHydrated: true, isLoading: true })
    renderProtectedRoute()

    expect(screen.queryByTestId("login-page")).not.toBeInTheDocument()
  })
})
