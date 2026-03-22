import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import SignupPage from "./SignupPage"

describe("Signup integration", () => {
  it("submits signup form and shows success message", async () => {
    const user = userEvent.setup()

    render(<SignupPage />)

    await user.type(screen.getByLabelText("Company name"), "Mock Corp")
    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Sign Up" }))

    expect(await screen.findByText(/successfully signed up/i)).toBeInTheDocument()
  })
})
