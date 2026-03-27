import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "sonner"

import ProtectedRoute from "./components/auth/ProtectedRoute"
import PublicRoute from "./components/auth/PublicRoute"
import Layout from "./components/layout/Layout"
import ErrorBoundary from "./components/shared/ErrorBoundary"
import NotFound from "./pages/NotFound"
import AuditLogPage from "./pages/AuditLog/AuditLogPage"
import DashboardPage from "./pages/Dashboard/DashboardPage"
import LandingPage from "./pages/Landing/LandingPage"
import LoginPage from "./pages/Login/LoginPage"
import PoliciesPage from "./pages/Policies/PoliciesPage"
import SettingsPage from "./pages/Settings/SettingsPage"
import IntegrationPage from "./pages/Integration/IntegrationPage"
import SignupPage from "./pages/Signup/SignupPage"
import ForgotPasswordPage from "./pages/ForgotPassword/ForgotPasswordPage"
import ResetPasswordPage from "./pages/ResetPassword/ResetPasswordPage"
import { useAuth } from "./hooks/useAuth"

function LandingOrDashboard() {
  const { isAuthenticated, isHydrated, isLoading } = useAuth()

  if (!isHydrated || isLoading) {
    return (
      <div className="h-full bg-dashboard-bg text-white flex items-center justify-center">
        <p className="text-text-muted">Loading...</p>
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  return <LandingPage />
}

function App() {
  return (
    <ErrorBoundary>
    <BrowserRouter>
      <Toaster
        position="top-right"
        theme="dark"
        richColors
        closeButton
        toastOptions={{
          style: {
            border: "1px solid #232A2A",
            background: "#141A1A",
            color: "#FFFFFF",
          },
        }}
      />
      <Routes>
        <Route path="/" element={<LandingOrDashboard />} />
        <Route
          path="/login"
          element={
            <PublicRoute>
              <LoginPage />
            </PublicRoute>
          }
        />
        <Route
          path="/signup"
          element={
            <PublicRoute>
              <SignupPage />
            </PublicRoute>
          }
        />
        <Route
          path="/forgot-password"
          element={
            <PublicRoute>
              <ForgotPasswordPage />
            </PublicRoute>
          }
        />
        <Route
          path="/reset-password"
          element={
            <PublicRoute>
              <ResetPasswordPage />
            </PublicRoute>
          }
        />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/integration" element={<IntegrationPage />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
