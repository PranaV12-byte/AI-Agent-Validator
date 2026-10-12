/**
 * A structurally valid JWT (header.payload.sig) with a far-future expiry.
 * Tests that put a token in localStorage must use this value so that the
 * AuthContext expiry check does not clear the session during hydration.
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
