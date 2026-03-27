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
  const detail = (error.response?.data as { detail?: string } | undefined)?.detail
  if (detail) return detail
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

type SessionProvider = () => { accessToken: string | null }
type RefreshHandler = () => Promise<void>

let getSession: SessionProvider = () => ({ accessToken: null })
let onUnauthorized: (() => void) | null = null
let refreshHandler: RefreshHandler | null = null

// Singleton promise prevents concurrent refresh races across multiple tabs / requests.
let refreshPromise: Promise<void> | null = null

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

function ensureRefresh(): Promise<void> {
  if (!refreshPromise) {
    const handler = refreshHandler
    refreshPromise = (
      handler ? handler() : Promise.reject(new Error("No refresh handler registered"))
    ).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

// Proactive refresh: silently refresh the access token before it expires.
apiClient.interceptors.request.use(async (config) => {
  const { accessToken } = getSession()

  if (accessToken && refreshHandler) {
    const exp = getTokenExpiry(accessToken)
    if (exp !== null && Date.now() / 1000 > exp - 60) {
      try {
        await ensureRefresh()
      } catch {
        // Refresh failed — let the request through; the 401 interceptor will clean up.
      }
    }
  }

  // Re-read after potential refresh so we attach the newest token.
  const { accessToken: freshToken } = getSession()
  if (freshToken) {
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

    const originalRequest = error.config as (AxiosRequestConfig & { _retry?: boolean; _retryCount?: number }) | undefined

    // Retry on 5xx / network errors (not on 401 — that path has its own logic below)
    if (isRetryable(error) && originalRequest) {
      const retryCount = originalRequest._retryCount ?? 0
      if (retryCount < MAX_RETRIES) {
        originalRequest._retryCount = retryCount + 1
        await new Promise((resolve) => setTimeout(resolve, 500 * Math.pow(2, retryCount)))
        return apiClient(originalRequest)
      }
    }

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      refreshHandler
    ) {
      originalRequest._retry = true
      try {
        await ensureRefresh()
        const { accessToken: freshToken } = getSession()
        if (freshToken && originalRequest.headers) {
          (originalRequest.headers as Record<string, string>).Authorization =
            `Bearer ${freshToken}`
        }
        return await apiClient(originalRequest)
      } catch {
        onUnauthorized?.()
      }
    } else if (error.response?.status === 401) {
      onUnauthorized?.()
    }

    return Promise.reject(error)
  },
)
