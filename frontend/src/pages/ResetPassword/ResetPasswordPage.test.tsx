import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"

import ResetPasswordPage from "./ResetPasswordPage"
import { server } from "../../mocks/server"

afterEach(cleanup)

function renderResetPassword(token = "mock-reset-token") {
  const initialPath = token ? `/reset-password?token=${token}` : "/reset-password"
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/login" element={<p data-testid="login-page">Login</p>} />
        <Route path="/forgot-password" element={<p data-testid="forgot-page">Forgot</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("ResetPasswordPage", () => {
  it("renders password fields and submit button when token is present", () => {
    renderResetPassword("mock-reset-token")
    expect(screen.getByLabelText("New password")).toBeInTheDocument()
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /update password/i })).toBeInTheDocument()
  })

  it("shows 'Invalid reset link.' when no token is in URL", () => {
    renderResetPassword("")
    expect(screen.getByText(/invalid reset link/i)).toBeInTheDocument()
  })

  it("shows 'Request a new reset link' button when no token", () => {
    renderResetPassword("")
    expect(screen.getByRole("button", { name: /request a new reset link/i })).toBeInTheDocument()
  })

  it("navigates to /forgot-password when no-token button is clicked", async () => {
    const user = userEvent.setup()
    renderResetPassword("")

    await user.click(screen.getByRole("button", { name: /request a new reset link/i }))
    await waitFor(() => {
      expect(screen.getByTestId("forgot-page")).toBeInTheDocument()
    })
  })

  it("shows inline mismatch error when passwords differ", async () => {
    const user = userEvent.setup()
    renderResetPassword()

    await user.type(screen.getByLabelText(/^new password/i), "Password1")
    await user.type(screen.getByLabelText(/confirm new password/i), "Password2")

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument()
  })

  it("disables submit button when passwords mismatch", async () => {
    const user = userEvent.setup()
    renderResetPassword()

    await user.type(screen.getByLabelText(/^new password/i), "Password1")
    await user.type(screen.getByLabelText(/confirm new password/i), "Different1")

    expect(screen.getByRole("button", { name: /update password/i })).toBeDisabled()
  })

  it("shows validation error for password with no digit", async () => {
    const user = userEvent.setup()
    renderResetPassword()

    await user.type(screen.getByLabelText(/^new password/i), "PasswordXX")
    await user.type(screen.getByLabelText(/confirm new password/i), "PasswordXX")
    await user.click(screen.getByRole("button", { name: /update password/i }))

    await waitFor(() => {
      expect(
        screen.getByText("Password must contain at least one letter and one number."),
      ).toBeInTheDocument()
    })
  })

  it("shows validation error for password with no letter", async () => {
    const user = userEvent.setup()
    renderResetPassword()

    await user.type(screen.getByLabelText(/^new password/i), "12345678")
    await user.type(screen.getByLabelText(/confirm new password/i), "12345678")
    await user.click(screen.getByRole("button", { name: /update password/i }))

    await waitFor(() => {
      expect(
        screen.getByText("Password must contain at least one letter and one number."),
      ).toBeInTheDocument()
    })
  })

  it("shows error when password is fewer than 8 characters", async () => {
    const user = userEvent.setup()
    renderResetPassword()

    await user.type(screen.getByLabelText(/^new password/i), "short")
    await user.type(screen.getByLabelText(/confirm new password/i), "short")
    await user.click(screen.getByRole("button", { name: /update password/i }))

    await waitFor(() => {
      expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument()
    })
  })

  it("redirects to /login?reset=1 after successful reset", async () => {
    const user = userEvent.setup()
    renderResetPassword("mock-reset-token")

    await user.type(screen.getByLabelText(/^new password/i), "NewPass123!")
    await user.type(screen.getByLabelText(/confirm new password/i), "NewPass123!")
    await user.click(screen.getByRole("button", { name: /update password/i }))

    await waitFor(() => {
      expect(screen.getByTestId("login-page")).toBeInTheDocument()
    })
  })

  it("shows API error message for invalid or expired token", async () => {
    server.use(
      http.post("*/api/v1/auth/reset-password", () => {
        return HttpResponse.json(
          { detail: "Invalid or expired reset token." },
          { status: 400 },
        )
      }),
    )

    const user = userEvent.setup()
    renderResetPassword("bad-token")

    await user.type(screen.getByLabelText(/^new password/i), "NewPass123!")
    await user.type(screen.getByLabelText(/confirm new password/i), "NewPass123!")
    await user.click(screen.getByRole("button", { name: /update password/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired reset token/i)).toBeInTheDocument()
    })
  })

  it("shows 'Request a new link' button when error mentions 'expired'", async () => {
    server.use(
      http.post("*/api/v1/auth/reset-password", () => {
        return HttpResponse.json(
          { detail: "Invalid or expired reset token." },
          { status: 400 },
        )
      }),
    )

    const user = userEvent.setup()
    renderResetPassword("expired-token")

    await user.type(screen.getByLabelText(/^new password/i), "NewPass123!")
    await user.type(screen.getByLabelText(/confirm new password/i), "NewPass123!")
    await user.click(screen.getByRole("button", { name: /update password/i }))

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /request a new link/i })).toBeInTheDocument()
    })
  })

  it("disables submit button while request is in flight", async () => {
    let resolveRequest!: () => void
    server.use(
      http.post("*/api/v1/auth/reset-password", () => {
        return new Promise<Response>((resolve) => {
          resolveRequest = () =>
            resolve(
              HttpResponse.json({ message: "Password updated successfully." }) as unknown as Response,
            )
        })
      }),
    )

    const user = userEvent.setup()
    renderResetPassword("mock-reset-token")

    await user.type(screen.getByLabelText(/^new password/i), "NewPass123!")
    await user.type(screen.getByLabelText(/confirm new password/i), "NewPass123!")

    const submitButton = screen.getByRole("button", { name: /update password/i })
    await user.click(submitButton)

    expect(screen.getByRole("button", { name: /updating password/i })).toBeDisabled()

    resolveRequest()
    await waitFor(() => {
      expect(screen.getByTestId("login-page")).toBeInTheDocument()
    })
  })
})
