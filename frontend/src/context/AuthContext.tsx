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

  // Ref keeps logout and performTokenRefresh stable (no dep on session state).
  const sessionRef = useRef<AuthSession | null>(null)
  sessionRef.current = session

  const logout = useCallback(() => {
    // Best-effort server-side revocation (fire-and-forget).
    const refreshToken = sessionRef.current?.refreshToken ?? null
    logoutRequest(refreshToken).catch(() => {/* ignore — local session cleared regardless */})
    localStorage.removeItem(STORAGE_KEY)
    setSession(null)
    setUser(null)
    setIsLoading(false)
  }, [])

  const performTokenRefresh = useCallback(async () => {
    const currentRefreshToken = sessionRef.current?.refreshToken
    if (!currentRefreshToken) {
      logout()
      return
    }
    try {
      const auth = await refreshTokenRequest(currentRefreshToken)
      const nextSession: AuthSession = {
        accessToken: auth.access_token,
        refreshToken: auth.refresh_token ?? null,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSession))
      setSession(nextSession)
    } catch {
      logout()
    }
  }, [logout])

  useEffect(() => {
    const restored = loadSession()
    setSession(restored)
    setIsHydrated(true)
    setIsLoading(Boolean(restored))
  }, [])

  const login = useCallback(async (input: LoginInput) => {
    const auth = await loginRequest(input)
    const nextSession: AuthSession = {
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token ?? null,
    }

    localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSession))
    setSession(nextSession)
    setIsLoading(true)
  }, [])

  const refreshProfile = useCallback(async () => {
    setIsLoading(true)
    try {
      const profile = await fetchTenantProfile()
      setUser(profile)
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        logout()
      }
      throw error
    } finally {
      setIsLoading(false)
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
    registerSessionProvider(() => ({ accessToken: session?.accessToken ?? null }))
  }, [session])

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
