import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { renderWithProviders } from "../../test/utils/renderWithProviders"
import IntegrationPage from "./IntegrationPage"

describe("IntegrationPage", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("hydrates API key prefix from auth profile", async () => {
    localStorage.setItem("safebot.auth.session", JSON.stringify({ accessToken: "mock-jwt" }))

    renderWithProviders(<IntegrationPage />)

    await waitFor(() => {
      expect(screen.getByText("mock1234")).toBeInTheDocument()
    })
  })

  it("copies the exact snippet text", async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })

    renderWithProviders(<IntegrationPage />)

    const code = (await screen.findAllByTestId("snippet-python-code"))[0]
    const copyButton = screen.getAllByTestId("snippet-python-copy")[0]

    await user.click(copyButton)

    expect(writeText).toHaveBeenCalledWith(code.textContent ?? "")
  })
})
