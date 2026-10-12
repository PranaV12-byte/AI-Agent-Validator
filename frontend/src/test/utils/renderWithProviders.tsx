import type { ReactElement } from "react"
import { render } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"

import { AuthProvider } from "../../context/AuthContext"
export { makeMockJwt, MOCK_JWT } from "./mockJwt"

export function renderWithProviders(ui: ReactElement) {
  return render(
    <MemoryRouter>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  )
}
