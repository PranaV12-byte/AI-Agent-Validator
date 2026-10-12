import axios from "axios"
import type { AxiosRequestConfig } from "axios"

const MAX_RETRIES = 2

function isRetryable(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  if (!error.response) return true // network / timeout error
  return error.response.status >= 500
}

/**
 * Extract a human-readable message from an API error.
 * Prefers the server's `detail` field, falls back to status-based messages.
 */
export function getErrorMessage(error: unknown, fallback = "An unexpected error occurred."): string {
  if (!axios.isAxiosError(error)) return fallback
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === "string") return detail
  if (!error.response) return "Network error — check your connection and try again."
  switch (error.response.status) {
    case 400: return "Invalid request. Please check your input."
    case 401: return "Your session has expired. Please sign in again."
    case 403: return "You do not have permission to perform this action."
    case 404: return "The requested resource was not found."
    case 409: return "A conflict occurred. This resource may already exist."
    case 429: return "Too many requests. Please wait a moment and try again."
    case 503: return "Service temporarily unavailable. Please try again shortly."
    default:  return error.response.status >= 500 ? "Server error. Please try again later." : fallback
  }
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"

type SessionProvider = () => { accessToken: string | null; generation?: number }
type RefreshHandler = () => Promise<void>

export type AuthAwareRequestConfig = AxiosRequestConfig & {
  _authGeneration?: number
  _authSessionPresent?: boolean
  _retry?: boolean
  _retryCount?: number
  _skipProactiveRefresh?: boolean
  _disableRetries?: boolean
  _logoutAccessToken?: string | null
}

let getSession: SessionProvider = () => ({ accessToken: null })
let onUnauthorized: (() => void) | null = null
let refreshHandler: RefreshHandler | null = null

// Singleton promise prevents concurrent refresh races across multiple tabs / requests.
let refreshPromise: { generation: number; promise: Promise<void> } | null = null

export function registerSessionProvider(provider: SessionProvider) {
  getSession = provider
}

export function registerUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

export function registerRefreshHandler(handler: RefreshHandler | null) {
  refreshHandler = handler
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

function getTokenExpiry(token: string): number | null {
  try {
    const parts = token.split(".")
    if (parts.length !== 3) return null
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: number }
    return payload.exp ?? null
  } catch {
    return null
  }
}

function currentGeneration(): number {
  return getSession().generation ?? 0
}

function ensureRefresh(generation: number): Promise<void> {
  if (refreshPromise?.generation === generation) return refreshPromise.promise

  const handler = refreshHandler
  const promise = (
    handler ? handler() : Promise.reject(new Error("No refresh handler registered"))
  ).finally(() => {
    if (refreshPromise?.promise === promise) refreshPromise = null
  })
  refreshPromise = { generation, promise }
  return promise
}

function isPublicAuthRequest(url: string | undefined): boolean {
  return /\/auth\/(?:login|signup|refresh|forgot-password|reset-password|verify-email|resend-verification)(?:\?|$)/.test(
    url ?? "",
  )
}

function isLogoutRequest(url: string | undefined): boolean {
  return /\/auth\/logout(?:\?|$)/.test(url ?? "")
}

function requestStillOwned(config: AuthAwareRequestConfig): boolean {
  return (
    (config._authGeneration === undefined || config._authGeneration === currentGeneration()) &&
    !config.signal?.aborted
  )
}

// Proactive refresh: silently refresh the access token before it expires.
apiClient.interceptors.request.use(async (config) => {
  const requestConfig = config as AuthAwareRequestConfig
  const session = getSession()
  const generation = requestConfig._authGeneration ?? session.generation ?? 0
  const publicAuthRequest = isPublicAuthRequest(config.url)
  const logoutRequest = isLogoutRequest(config.url)
  requestConfig._authGeneration = generation
  requestConfig._authSessionPresent = requestConfig._authSessionPresent ??
    Boolean(session.accessToken && !publicAuthRequest && !logoutRequest)
  if (!logoutRequest && generation !== (session.generation ?? 0)) {
    throw new axios.CanceledError("Authentication session changed")
  }

  // Skip proactive refresh for requests that are themselves part of the refresh flow
  // to prevent a circular deadlock: refresh request → interceptor → ensureRefresh() → same refreshPromise
  const skip = requestConfig._skipProactiveRefresh || publicAuthRequest || logoutRequest

  if (!skip && session.accessToken && refreshHandler) {
    const exp = getTokenExpiry(session.accessToken)
    if (exp !== null && Date.now() / 1000 > exp - 60) {
      try {
        await ensureRefresh(generation)
      } catch {
        // Refresh failed — let the request through; the 401 interceptor will clean up.
      }
    }
  }

  if (!logoutRequest && generation !== currentGeneration()) {
    throw new axios.CanceledError("Authentication session changed")
  }

  // Re-read after potential refresh so we attach the newest token.
  const { accessToken: freshToken } = getSession()
  if (publicAuthRequest || logoutRequest) {
    // Public auth calls never carry ambient credentials. A logout may carry
    // only the access token explicitly snapshotted from the session being
    // ended; never substitute whichever session is current at dispatch time.
    delete config.headers.Authorization
    if (logoutRequest && requestConfig._logoutAccessToken) {
      config.headers.Authorization = `Bearer ${requestConfig._logoutAccessToken}`
    }
  } else if (freshToken) {
    config.headers.Authorization = `Bearer ${freshToken}`
  }

  return config
})

// Reactive refresh: on 401, attempt a token refresh once then retry the original request.
// Also retries 5xx and network errors up to MAX_RETRIES times with exponential backoff.
apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error)
    }

    if (axios.isCancel(error)) return Promise.reject(error)

    const originalRequest = error.config as AuthAwareRequestConfig | undefined
    if (originalRequest && !requestStillOwned(originalRequest)) {
      return Promise.reject(error)
    }

    // Retry on 5xx / network errors (not on 401 — that path has its own logic below)
    if (
      isRetryable(error) &&
      originalRequest &&
      !originalRequest.signal?.aborted &&
      !originalRequest._disableRetries
    ) {
      const retryCount = originalRequest._retryCount ?? 0
      if (retryCount < MAX_RETRIES) {
        originalRequest._retryCount = retryCount + 1
        await new Promise((resolve) => setTimeout(resolve, 500 * Math.pow(2, retryCount)))
        return apiClient(originalRequest)
      }
    }

    const isAuthLifecycleRequest =
      isPublicAuthRequest(originalRequest?.url) || isLogoutRequest(originalRequest?.url)
    const requestHadSession = originalRequest?._authSessionPresent ?? true
    if (
      error.response?.status === 401 &&
      originalRequest &&
      requestHadSession &&
      !isAuthLifecycleRequest &&
      !originalRequest._retry &&
      refreshHandler
    ) {
      originalRequest._retry = true
      const generation = originalRequest._authGeneration ?? currentGeneration()
      try {
        await ensureRefresh(generation)
      } catch {
        if (requestStillOwned(originalRequest)) onUnauthorized?.()
        return Promise.reject(error)
      }

      if (!requestStillOwned(originalRequest)) return Promise.reject(error)
      const { accessToken: freshToken } = getSession()
      if (!freshToken) {
        onUnauthorized?.()
        return Promise.reject(error)
      }
      if (originalRequest.headers) {
        (originalRequest.headers as Record<string, string>).Authorization =
          `Bearer ${freshToken}`
      }
      return apiClient(originalRequest)
    } else if (
      error.response?.status === 401 &&
      requestHadSession &&
      !isAuthLifecycleRequest &&
      (!originalRequest || requestStillOwned(originalRequest))
    ) {
      onUnauthorized?.()
    }

    return Promise.reject(error)
  },
)
