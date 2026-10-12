import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { StrictMode } from "react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"

import EmailVerificationPage from "./EmailVerificationPage"
import { server } from "../../mocks/server"

afterEach(cleanup)

function renderEmailVerification(token?: string, strictMode = false) {
  const path = token ? `/verify-email?token=${token}` : "/verify-email"
  const app = (
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/verify-email" element={<EmailVerificationPage />} />
        <Route path="/login" element={<p data-testid="login-page">Login</p>} />
      </Routes>
    </MemoryRouter>
  )
  return render(strictMode ? <StrictMode>{app}</StrictMode> : app)
}

describe("EmailVerificationPage", () => {
  it("verifies a valid token and shows success message", async () => {
    renderEmailVerification("mock-verify-token")

    await waitFor(() => {
      expect(
        screen.getByText(/your email has been verified/i),
      ).toBeInTheDocument()
    })
  })

  it("shares one single-use verification request across StrictMode effect replay", async () => {
    let verifyCalls = 0
    server.use(
      http.post("*/api/v1/auth/verify-email", () => {
        verifyCalls += 1
        return verifyCalls === 1
          ? HttpResponse.json({ message: "Email verified successfully." })
          : HttpResponse.json({ detail: "Invalid or expired verification link." }, { status: 400 })
      }),
    )

    renderEmailVerification("single-use-token", true)

    await waitFor(() => {
      expect(screen.getByText(/your email has been verified/i)).toBeInTheDocument()
    })
    expect(verifyCalls).toBe(1)
  })

  it("shows 'already verified' message for an already-verified token", async () => {
    renderEmailVerification("already-verified-token")

    await waitFor(() => {
      expect(screen.getByText(/already verified/i)).toBeInTheDocument()
    })
  })

  it("shows error state for an invalid token", async () => {
    renderEmailVerification("bad-token")

    await waitFor(() => {
      expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument()
    })
  })

  it("shows no-token state when token is absent", () => {
    renderEmailVerification()
    expect(screen.getByText(/no verification token/i)).toBeInTheDocument()
  })

  it("navigates to /login after success", async () => {
    const user = userEvent.setup()
    renderEmailVerification("mock-verify-token")

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /go to sign in/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole("button", { name: /go to sign in/i }))
    await waitFor(() => {
      expect(screen.getByTestId("login-page")).toBeInTheDocument()
    })
  })

  it("shows resend form on error and submits successfully", async () => {
    const user = userEvent.setup()
    renderEmailVerification("invalid-token")

    await waitFor(() => {
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText(/email address/i), "user@example.com")
    await user.click(screen.getByRole("button", { name: /resend verification link/i }))

    await waitFor(() => {
      expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument()
    })
  })

  it("uses a local resend verification URL returned by the development API", async () => {
    const user = userEvent.setup()
    server.use(
      http.post("*/api/v1/auth/resend-verification", () =>
        HttpResponse.json({
          message: "If that email is registered and unverified, a new link has been sent.",
          verification_url: "http://localhost:5173/verify-email?token=resend-token",
        }),
      ),
      http.post("*/api/v1/auth/verify-email", async ({ request }) => {
        const body = (await request.json()) as { token?: string }
        if (body.token === "resend-token") {
          return HttpResponse.json({ message: "Email verified successfully." })
        }
        return HttpResponse.json({ detail: "Invalid or expired verification link." }, { status: 400 })
      }),
    )
    renderEmailVerification("invalid-token")

    await waitFor(() => expect(screen.getByLabelText(/email address/i)).toBeInTheDocument())
    await user.type(screen.getByLabelText(/email address/i), "user@example.com")
    await user.click(screen.getByRole("button", { name: /resend verification link/i }))

    await waitFor(() => expect(screen.getByText(/your email has been verified/i)).toBeInTheDocument())
  })

  it("shows error when resend API fails", async () => {
    server.use(
      http.post("*/api/v1/auth/resend-verification", () => {
        return HttpResponse.json({ detail: "Bad request" }, { status: 400 })
      }),
    )

    const user = userEvent.setup()
    renderEmailVerification("invalid-token")

    await waitFor(() => {
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText(/email address/i), "user@example.com")
    await user.click(screen.getByRole("button", { name: /resend verification link/i }))

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    })
  })

  it("shows loading state while verifying token", async () => {
    let resolveVerify: (() => void) | null = null
    server.use(
      http.post("*/api/v1/auth/verify-email", () => {
        return new Promise<Response>((resolve) => {
          resolveVerify = () =>
            resolve(
              HttpResponse.json({ message: "Email verified successfully. You can now sign in." }) as unknown as Response,
            )
        })
      }),
    )

    renderEmailVerification("mock-verify-token")

    // Initially shows loading text
    expect(screen.getByText(/verifying your email/i)).toBeInTheDocument()

    // Wait for MSW to have captured the request (resolveVerify is assigned inside the handler)
    await waitFor(() => {
      expect(resolveVerify).not.toBeNull()
    })

    resolveVerify!()
    await waitFor(() => {
      expect(screen.getByText(/your email has been verified/i)).toBeInTheDocument()
    })
  })
})
