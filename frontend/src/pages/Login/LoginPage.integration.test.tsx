import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it } from "vitest"

import { AuthProvider } from "../../context/AuthContext"
import { server } from "../../mocks/server"
import DashboardPage from "../Dashboard/DashboardPage"
import LoginPage from "./LoginPage"

describe("Login integration", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("logs in through mocked network and navigates to dashboard", async () => {
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "TestPass123!")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    await waitFor(() => {
      expect(screen.getByText("Security Overview")).toBeInTheDocument()
    })
  })

  it("shows credentials error when login API returns 401", async () => {
    const user = userEvent.setup()

    server.use(
      http.post("*/api/v1/auth/login", () => {
        return HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 })
      }),
    )

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.type(screen.getByLabelText("Email"), "mock@example.com")
    await user.type(screen.getByLabelText("Password"), "wrong-pass")
    await user.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByText("Invalid email or password.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument()
  })
})
