import type { ReactNode } from "react"
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import axios from "axios"

import { fetchTenantProfile, loginRequest } from "../services/authService"
import {
  registerSessionProvider,
  registerUnauthorizedHandler,
} from "../services/apiClient"
import type { TenantProfile } from "../types/api"

type AuthSession = {
  accessToken: string
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

function loadSession(): AuthSession | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as AuthSession
    if (!parsed.accessToken) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [user, setUser] = useState<TenantProfile | null>(null)
  const [isHydrated, setIsHydrated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setSession(null)
    setUser(null)
    setIsLoading(false)
  }, [])

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
    registerUnauthorizedHandler(() => {
      logout()
      window.location.replace("/login")
    })

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
