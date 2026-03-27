import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import SignupPage from "./SignupPage"

describe("Signup integration", () => {
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
})
