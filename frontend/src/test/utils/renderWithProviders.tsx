import type { ReactElement } from "react"
import { render } from "@testing-library/react"

import { AuthProvider } from "../../context/AuthContext"

/**
 * A structurally valid JWT (header.payload.sig) with a far-future expiry.
 * Tests that put a token in localStorage must use this constant so that
 * the isTokenExpired() check in AuthContext doesn't clear the session.
 */
export function makeMockJwt(sub = "tenant-1"): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
  const payload = btoa(
    JSON.stringify({ sub, exp: 9999999999, iat: 1000000000, jti: "mock-jti" }),
  )
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
  return `${header}.${payload}.mock-signature`
}

export const MOCK_JWT = makeMockJwt()

export function renderWithProviders(ui: ReactElement) {
  return render(<AuthProvider>{ui}</AuthProvider>)
}
