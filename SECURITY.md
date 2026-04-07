# Security Policy

## Supported Versions

Safebot is currently in MVP / pre-production status. Only the `main` branch receives security fixes.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities. Email the maintainer directly or use GitHub's private security advisory feature. We aim to respond within 48 hours and release a fix within 7 days for confirmed critical issues.

---

## Known Limitations and Mitigations

### 1. JWT Storage in localStorage (accepted risk for MVP)

**Risk:** Access tokens are stored in `localStorage`, which is accessible to JavaScript. Any successful XSS attack on the app or a malicious third-party script could read tokens.

**Mitigations in place:**
- Content Security Policy (`script-src 'self'`) is configured in the production Nginx, blocking third-party script injection.
- JWT access tokens expire in 15 minutes (`JWT_EXPIRE_MINUTES=15`). A stolen token has a short window of usability.
- Refresh tokens are stored in Redux/context state only (not persisted), so a page reload terminates the session.

**Planned fix:** Migrate to `httpOnly` SameSite=Strict cookies for token storage post-MVP. This requires adding CSRF protection simultaneously (see item 2).

---

### 2. CSRF Protection Not Required (current architecture)

**Current state:** All API calls use the `Authorization: Bearer <token>` header. Browsers never automatically attach `Authorization` headers on cross-origin requests, so CSRF attacks are not possible in the current architecture.

**Constraint:** If the authentication mechanism is ever migrated to cookie-based tokens (see item 1), CSRF protection **must** be added at the same time. The recommended approach is the double-submit cookie pattern or SameSite=Strict with a synchronizer token.

---

### 3. API Key Lookup Timing Side-Channel (accepted)

**Risk:** The API key verification path uses an in-process LRU cache. Cache hits return faster than cache misses (which go through bcrypt). In theory, this timing difference could reveal information.

**Why it is acceptable:** The cache key is `SHA-256(raw_key + ":" + stored_hash)`. An attacker cannot probe a specific cache entry without already knowing the raw key *and* its bcrypt hash — at which point they have no need to probe the cache. The bcrypt comparison itself is constant-time.

---

### 4. Password Reset URL in Development Responses

**Risk:** When `ENVIRONMENT=development` or `ENVIRONMENT=test`, the `POST /auth/forgot-password` endpoint returns the password reset URL in the response body. This is intentional for local development.

**Protection:** The application startup (`main.py` lifespan) refuses to start with `ENVIRONMENT=production` if `FRONTEND_URL` is set to a localhost address, preventing accidental `development` mode in production.

**Invariant:** Never deploy with `ENVIRONMENT=development` in production. The startup validation enforces this.

---

### 5. Algorand Testnet Default

**Risk:** `ALGORAND_NETWORK` defaults to `"testnet"`. Audit events written to testnet have no legal or compliance value.

**Protection:** The application startup rejects launches where `ENVIRONMENT=production`, `ALGORAND_APP_ID != 0`, and `ALGORAND_NETWORK != "mainnet"`. This prevents silent testnet writes in production.

---

## Security Headers

All HTTP responses include:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (non-dev only) |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; ...` (Nginx, production) |

## Rate Limiting

All public endpoints are rate-limited via SlowAPI:
- Auth endpoints: 5–20 requests/minute
- API key rotation: 3 requests/hour
- Hook validation: 60 requests/minute per API key (configurable)
