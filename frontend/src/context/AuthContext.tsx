import type { ReactNode } from "react"
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import axios from "axios"

import { fetchTenantProfile, loginRequest, logoutRequest, refreshTokenRequest } from "../services/authService"
import {
  registerRefreshHandler,
  registerSessionProvider,
  registerUnauthorizedHandler,
} from "../services/apiClient"
import type { TenantProfile } from "../types/api"

type AuthSession = {
  accessToken: string
  refreshToken: string | null
}

type LoginInput = {
  email: string
  password: string
}

type AuthContextValue = {
  isAuthenticated: boolean
  isHydrated: boolean
  isLoading: boolean
  accessToken: string | null
  user: TenantProfile | null
  login: (input: LoginInput) => Promise<void>
  refreshProfile: () => Promise<void>
  logout: () => void
}

const STORAGE_KEY = "safebot.auth.session"

const AuthContext = createContext<AuthContextValue | null>(null)

function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split(".")
    if (parts.length !== 3) return true
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: number }
    if (!payload.exp) return false
    // 30-second buffer to avoid accepting tokens that expire mid-request
    return Date.now() / 1000 > payload.exp - 30
  } catch {
    return true
  }
}

function loadSession(): AuthSession | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as Partial<AuthSession>
    if (!parsed.accessToken) return null
    const refreshToken = parsed.refreshToken ?? null

    if (isTokenExpired(parsed.accessToken)) {
      if (!refreshToken) {
        // No way to silently refresh — force re-login.
        localStorage.removeItem(STORAGE_KEY)
        return null
      }
      // Expired access token but valid refresh token — keep session for silent refresh.
      return { accessToken: parsed.accessToken, refreshToken }
    }
    return { accessToken: parsed.accessToken, refreshToken }
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [user, setUser] = useState<TenantProfile | null>(null)
  const [isHydrated, setIsHydrated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Request handlers read from refs so token publication is synchronous with
  // login/refresh completion and independent of React's next render.
  const sessionRef = useRef<AuthSession | null>(null)
  const sessionGenerationRef = useRef(0)
  const sessionOwnerRef = useRef(0)

  const logout = useCallback(() => {
    const endingSession = sessionRef.current
    const generation = ++sessionGenerationRef.current

    if (endingSession) {
      // Snapshot both credentials before clearing the session. The refresh
      // token revokes its family; the access token also covers legacy sessions
      // that predate refresh-token storage.
      logoutRequest(endingSession.refreshToken, endingSession.accessToken).catch(() => {
        console.warn("Server-side logout failed; refresh token may remain valid until TTL expiry.")
      })
      queueMicrotask(() => {
        if (sessionGenerationRef.current === generation) {
          sessionRef.current = null
          sessionOwnerRef.current = generation
        }
      })
    } else {
      sessionRef.current = null
      sessionOwnerRef.current = generation
    }

    localStorage.removeItem(STORAGE_KEY)
    setSession(null)
    setUser(null)
    setIsLoading(false)
  }, [])

  const performTokenRefresh = useCallback(async () => {
    const generation = sessionGenerationRef.current
    const sessionBeingRefreshed = sessionRef.current
    const currentRefreshToken = sessionBeingRefreshed?.refreshToken
    if (sessionOwnerRef.current !== generation) {
      // A request from the outgoing session can reach this handler after a
      // replacement has begun. It must not log out the incoming session.
      return
    }
    if (!sessionBeingRefreshed) {
      // There is no active session to refresh or invalidate. In particular,
      // do not cancel a login that is already in flight.
      return
    }
    if (!currentRefreshToken) {
      if (sessionGenerationRef.current === generation) logout()
      return
    }
    try {
      const auth = await refreshTokenRequest(currentRefreshToken)
      if (
        sessionGenerationRef.current !== generation ||
        sessionOwnerRef.current !== generation ||
        sessionRef.current?.refreshToken !== currentRefreshToken
      ) {
        return
      }
      const nextSession: AuthSession = {
        accessToken: auth.access_token,
        refreshToken: auth.refresh_token ?? null,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSession))
      sessionRef.current = nextSession
      sessionOwnerRef.current = generation
      setSession(nextSession)
    } catch {
      if (
        sessionGenerationRef.current === generation &&
        sessionOwnerRef.current === generation &&
        sessionRef.current?.refreshToken === currentRefreshToken
      ) {
        logout()
      }
    }
  }, [logout])

  useEffect(() => {
    const restored = loadSession()
    sessionOwnerRef.current = sessionGenerationRef.current
    sessionRef.current = restored
    setSession(restored)
    setIsHydrated(true)
    setIsLoading(Boolean(restored))
  }, [])

  const login = useCallback(async (input: LoginInput) => {
    const previousSession = sessionRef.current
    const generation = ++sessionGenerationRef.current
    if (previousSession) {
      logoutRequest(previousSession.refreshToken, previousSession.accessToken).catch(() => {
        console.warn("Server-side logout failed; refresh token may remain valid until TTL expiry.")
      })
      queueMicrotask(() => {
        if (sessionGenerationRef.current === generation) {
          sessionRef.current = null
          sessionOwnerRef.current = generation
        }
      })
    } else {
      sessionRef.current = null
      sessionOwnerRef.current = generation
    }
    localStorage.removeItem(STORAGE_KEY)
    setSession(null)
    setUser(null)
    setIsLoading(true)

    let auth: Awaited<ReturnType<typeof loginRequest>>
    try {
      auth = await loginRequest(input)
    } catch (error) {
      if (sessionGenerationRef.current === generation) setIsLoading(false)
      throw error
    }
    if (sessionGenerationRef.current !== generation) return

    const nextSession: AuthSession = {
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token ?? null,
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSession))
    sessionRef.current = nextSession
    sessionOwnerRef.current = generation
    setSession(nextSession)
    setIsLoading(true)
  }, [])

  const refreshProfile = useCallback(async () => {
    const generation = sessionGenerationRef.current
    if (!sessionRef.current || sessionOwnerRef.current !== generation) {
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    try {
      const profile = await fetchTenantProfile()
      if (
        sessionGenerationRef.current === generation &&
        sessionOwnerRef.current === generation &&
        sessionRef.current
      ) {
        setUser(profile)
      }
    } catch (error) {
      if (
        sessionGenerationRef.current === generation &&
        sessionOwnerRef.current === generation &&
        sessionRef.current &&
        axios.isAxiosError(error) &&
        error.response?.status === 401
      ) {
        logout()
      }
      throw error
    } finally {
      if (sessionGenerationRef.current === generation) setIsLoading(false)
    }
  }, [logout])

  useEffect(() => {
    if (!session?.accessToken) {
      return
    }

    async function loadProfile() {
      try {
        await refreshProfile()
      } catch {
        // refreshProfile handles 401 cleanup and state updates.
      }
    }

    void loadProfile()
  }, [refreshProfile, session?.accessToken])

  useEffect(() => {
    registerSessionProvider(() => ({
      accessToken: sessionRef.current?.accessToken ?? null,
      // Keep the generation paired with the token currently in the ref. During
      // logout/replacement the old token is retained briefly so its refresh
      // token can be revoked; requests queued in that window must still be
      // recognized as belonging to the old session, not the incoming one.
      generation: sessionRef.current
        ? sessionOwnerRef.current
        : sessionGenerationRef.current,
    }))
    return () => registerSessionProvider(() => ({ accessToken: null }))
  }, [])

  useEffect(() => {
    registerRefreshHandler(performTokenRefresh)
    return () => {
      registerRefreshHandler(null)
    }
  }, [performTokenRefresh])

  useEffect(() => {
    registerUnauthorizedHandler(logout)
    return () => {
      registerUnauthorizedHandler(null)
    }
  }, [logout])

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: Boolean(session?.accessToken && user),
      isHydrated,
      isLoading,
      accessToken: session?.accessToken ?? null,
      user,
      login,
      refreshProfile,
      logout,
    }),
    [isHydrated, isLoading, login, logout, refreshProfile, session, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuthContext() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider")
  }
  return context
}
