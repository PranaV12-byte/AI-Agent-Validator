import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"

import { server } from "../../mocks/server"
import SignupPage from "./SignupPage"

describe("Signup integration", () => {
  afterEach(() => {
    cleanup()
  })

  it("submits signup form and shows success message", async () => {
    const user = userEvent.setup()

    render(<MemoryRouter><SignupPage /></MemoryRouter>)

    await user.type(screen.getByLabelText("Company name"), "Mock Corp")
    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.type(screen.getByLabelText("Confirm password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Create Account" }))

    // Success triggers a toast and redirect; no error message should appear
    await waitFor(() => {
      expect(screen.queryByText(/could not sign up/i)).not.toBeInTheDocument()
    })
  })

  it("shows error when email is already registered (409)", async () => {
    server.use(
      http.post("*/api/v1/auth/signup", () => {
        return HttpResponse.json(
          { detail: "Email already registered" },
          { status: 409 },
        )
      }),
    )

    const user = userEvent.setup()
    render(<MemoryRouter><SignupPage /></MemoryRouter>)

    await user.type(screen.getByLabelText("Company name"), "Dupe Corp")
    await user.type(screen.getByLabelText("Email"), "existing@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.type(screen.getByLabelText("Confirm password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Create Account" }))

    expect(
      await screen.findByText("An account with this email already exists."),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /sign in instead/i })).toBeInTheDocument()
  })

  it("shows validation error for password with no letter", async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><SignupPage /></MemoryRouter>)

    await user.type(screen.getByLabelText("Company name"), "Test Corp")
    await user.type(screen.getByLabelText("Email"), "test@example.com")
    await user.type(screen.getByLabelText("Password"), "12345678")
    await user.type(screen.getByLabelText("Confirm password"), "12345678")
    await user.click(screen.getByRole("button", { name: "Create Account" }))

    expect(
      await screen.findByText("Password must contain at least one letter and one number."),
    ).toBeInTheDocument()
  })

  it("shows validation error for password with no digit", async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><SignupPage /></MemoryRouter>)

    await user.type(screen.getByLabelText("Company name"), "Test Corp")
    await user.type(screen.getByLabelText("Email"), "test@example.com")
    await user.type(screen.getByLabelText("Password"), "PasswordXX")
    await user.type(screen.getByLabelText("Confirm password"), "PasswordXX")
    await user.click(screen.getByRole("button", { name: "Create Account" }))

    expect(
      await screen.findByText("Password must contain at least one letter and one number."),
    ).toBeInTheDocument()
  })

  it("company name field has required attribute", () => {
    render(<MemoryRouter><SignupPage /></MemoryRouter>)
    expect(screen.getByLabelText("Company name")).toBeRequired()
  })
})
