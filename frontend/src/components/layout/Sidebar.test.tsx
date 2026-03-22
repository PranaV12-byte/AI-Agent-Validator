import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import Sidebar from "./Sidebar"
import { useAuth } from "../../hooks/useAuth"

vi.mock("../../hooks/useAuth", () => ({
  useAuth: vi.fn(),
}))

describe("Sidebar", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      isHydrated: true,
      isLoading: false,
      accessToken: null,
      user: null,
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
  })

  it("shows fallback profile text when user is null", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText("Tenant")).toBeInTheDocument()
    expect(screen.getByText("--")).toBeInTheDocument()
  })
})
