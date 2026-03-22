import type { ReactElement } from "react"
import { render } from "@testing-library/react"

import { AuthProvider } from "../../context/AuthContext"

export function renderWithProviders(ui: ReactElement) {
  return render(<AuthProvider>{ui}</AuthProvider>)
}
