import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"

import { useAuth } from "../../hooks/useAuth"

function PublicRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isHydrated, isLoading } = useAuth()

  if (!isHydrated || isLoading) {
    return (
      <div className="h-full bg-dashboard-bg text-white flex items-center justify-center">
        <p className="text-text-muted">Restoring session...</p>
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}

export default PublicRoute
