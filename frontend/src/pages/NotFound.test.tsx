import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useAuth } from "../hooks/useAuth"
import NotFound from "./NotFound"

vi.mock("../hooks/useAuth", () => ({ useAuth: vi.fn() }))

afterEach(() => cleanup())

describe("NotFound", () => {
  it("shows 'Go to Dashboard' link when authenticated", () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      isLoading: false,
      accessToken: "tok",
      user: null,
      login: vi.fn(),
      refreshProfile: vi.fn(),
      logout: vi.fn(),
    })
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    )
    expect(screen.getByRole("link", { name: /Go to Dashboard/i })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Go to Home/i })).not.toBeInTheDocument()
  })

  it("shows 'Go to Home' link when not authenticated", () => {
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
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    )
    expect(screen.getByRole("link", { name: /Go to Home/i })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Go to Dashboard/i })).not.toBeInTheDocument()
  })
})
