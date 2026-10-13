import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { AuthProvider } from "../../context/AuthContext"
import PublicRoute from "../../components/auth/PublicRoute"
import { server } from "../../mocks/server"
import { MOCK_JWT } from "../../test/utils/renderWithProviders"
import DashboardPage from "../Dashboard/DashboardPage"
import LoginPage from "./LoginPage"

describe("Login integration", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
  })

  it("logs in through mocked network and navigates to dashboard", async () => {
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    await waitFor(() => {
      expect(screen.getByText("Your AI Protection Dashboard")).toBeInTheDocument()
    })
  })

  it("shows a verify-first sign-in message after an email change without a local link", () => {
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login?verification=pending"]}>
          <LoginPage />
        </MemoryRouter>
      </AuthProvider>,
    )

    expect(screen.getByRole("status")).toHaveTextContent(
      /verify your new address using the link sent to your inbox/i,
    )
  })

  it("keeps the login form and email after a rejected attempt, then allows a successful retry", async () => {
    const user = userEvent.setup()
    let attempts = 0

    server.use(
      http.post("*/api/v1/auth/login", () => {
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 })
        }
        return HttpResponse.json({
          access_token: MOCK_JWT,
          token_type: "bearer",
          refresh_token: "mock-refresh",
        })
      }),
    )

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/dashboard" element={<div>Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "wrong-pass")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toHaveValue("mock@example.com")
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByText("Dashboard")).toBeInTheDocument()
    expect(attempts).toBe(2)
  })

  it("disables submit button while request is in progress", async () => {
    let resolveLogin!: () => void
    const loginBarrier = new Promise<void>((r) => { resolveLogin = r })

    server.use(
      http.post("*/api/v1/auth/login", async () => {
        await loginBarrier
        return HttpResponse.json({
          access_token: MOCK_JWT,
          token_type: "bearer",
          refresh_token: "mock-refresh",
        })
      }),
    )

    const user = userEvent.setup()
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
            <Route path="/dashboard" element={<div>Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")

    try {
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled()
      })
    } finally {
      resolveLogin()
    }
  })

  it("shows error message when API returns a non-401 error", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () => {
        // 400 is non-retryable so no backoff delay in test
        return HttpResponse.json({ detail: "Bad request" }, { status: 400 })
      }),
    )

    const user = userEvent.setup()
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByText("Bad request")).toBeInTheDocument()
  })

  it("navigates to redirect_uri after successful login", async () => {
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login?redirect_uri=/audit-log"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/audit-log" element={<div>Audit Log Page</div>} />
            <Route path="/dashboard" element={<div>Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    await waitFor(() => {
      expect(screen.getByText("Audit Log Page")).toBeInTheDocument()
    })
  })

  it("toggles password visibility on login form", () => {
    render(
      <AuthProvider>
        <MemoryRouter><LoginPage /></MemoryRouter>
      </AuthProvider>
    )

    const passwordInput = screen.getByLabelText("Password")
    expect(passwordInput).toHaveAttribute("type", "password")

    fireEvent.click(screen.getByRole("button", { name: /Show password/i }))
    expect(passwordInput).toHaveAttribute("type", "text")

    fireEvent.click(screen.getByRole("button", { name: /Hide password/i }))
    expect(passwordInput).toHaveAttribute("type", "password")
  })

  it("ignores unsafe redirect_uri and falls back to /dashboard", async () => {
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login?redirect_uri=//evil.com"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<div>Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument()
    })
  })
})
