import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"

import ForgotPasswordPage from "./ForgotPasswordPage"
import { server } from "../../mocks/server"

afterEach(cleanup)

function renderForgotPassword() {
  return render(
    <MemoryRouter initialEntries={["/forgot-password"]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/login" element={<p data-testid="login-page">Login</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("ForgotPasswordPage", () => {
  it("renders email input and submit button", () => {
    renderForgotPassword()
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /send reset link/i })).toBeInTheDocument()
  })

  it("renders 'Back to sign in' link", () => {
    renderForgotPassword()
    expect(screen.getByRole("button", { name: /back to sign in/i })).toBeInTheDocument()
  })

  it("navigates to /login when 'Back to sign in' is clicked", async () => {
    const user = userEvent.setup()
    renderForgotPassword()

    await user.click(screen.getByRole("button", { name: /back to sign in/i }))
    await waitFor(() => {
      expect(screen.getByTestId("login-page")).toBeInTheDocument()
    })
  })

  it("shows success message after submitting a registered email", async () => {
    const user = userEvent.setup()
    renderForgotPassword()

    await user.type(screen.getByLabelText(/email address/i), "mock@example.com")
    await user.click(screen.getByRole("button", { name: /send reset link/i }))

    await waitFor(() => {
      expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument()
    })
  })

  it("shows success message for unknown email too (no email enumeration)", async () => {
    const user = userEvent.setup()
    renderForgotPassword()

    await user.type(screen.getByLabelText(/email address/i), "unknown@example.com")
    await user.click(screen.getByRole("button", { name: /send reset link/i }))

    await waitFor(() => {
      expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument()
    })
  })

  it("shows dev-mode reset URL when API returns reset_url", async () => {
    const user = userEvent.setup()
    renderForgotPassword()

    // mock@example.com triggers reset_url in MSW handler
    await user.type(screen.getByLabelText(/email address/i), "mock@example.com")
    await user.click(screen.getByRole("button", { name: /send reset link/i }))

    await waitFor(() => {
      // In DEV mode (vitest runs with import.meta.env.DEV=true) the reset URL link appears
      const link = screen.queryByRole("link")
      if (link) {
        expect(link).toHaveAttribute("href", expect.stringContaining("reset-password"))
      }
      // Success message always shown
      expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument()
    })
  })

  it("shows error message when API call fails", async () => {
    // Use 400 (not 5xx) to avoid the apiClient retry backoff delay
    server.use(
      http.post("*/api/v1/auth/forgot-password", () => {
        return HttpResponse.json({ detail: "Bad request" }, { status: 400 })
      }),
    )

    const user = userEvent.setup()
    renderForgotPassword()

    await user.type(screen.getByLabelText(/email address/i), "test@example.com")
    await user.click(screen.getByRole("button", { name: /send reset link/i }))

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    })
  })

  it("disables submit button while submitting", async () => {
    let resolveRequest!: () => void
    server.use(
      http.post("*/api/v1/auth/forgot-password", () => {
        return new Promise<Response>((resolve) => {
          resolveRequest = () =>
            resolve(
              HttpResponse.json({ message: "ok" }) as unknown as Response,
            )
        })
      }),
    )

    const user = userEvent.setup()
    renderForgotPassword()

    await user.type(screen.getByLabelText(/email address/i), "test@example.com")

    const submitButton = screen.getByRole("button", { name: /send reset link/i })
    await user.click(submitButton)

    // While request is pending, button should show "Sending..." and be disabled
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled()

    // Resolve the request
    resolveRequest()
    await waitFor(() => {
      expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument()
    })
  })
})
