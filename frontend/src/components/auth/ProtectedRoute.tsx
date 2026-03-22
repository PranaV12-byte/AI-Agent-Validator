import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router-dom"

import { useAuth } from "../../hooks/useAuth"

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isHydrated, isLoading } = useAuth()
  const location = useLocation()

  if (!isHydrated || isLoading) {
    return (
      <div className="h-full bg-dashboard-bg text-white flex items-center justify-center">
        <p className="text-text-muted">Restoring session...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    const redirect = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?redirect_uri=${redirect}`} replace />
  }

  return <>{children}</>
}

export default ProtectedRoute
