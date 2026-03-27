import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import PolicyPage from "./PolicyPage"

describe("PolicyPage integration", () => {
  it("hydrates config from GET and deploys changes via PUT", async () => {
    const user = userEvent.setup()

    render(<PolicyPage />)

    await waitFor(() => {
      expect(screen.getByText("Last updated: version 1.0")).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText("Block AI manipulation attempts"))
    await user.click(screen.getByTestId("deploy-changes-button"))

    await waitFor(() => {
      expect(screen.getByText("Last updated: version 2.0")).toBeInTheDocument()
    })
  })
})
