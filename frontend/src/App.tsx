import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "sonner"

import ProtectedRoute from "./components/auth/ProtectedRoute"
import PublicRoute from "./components/auth/PublicRoute"
import Layout from "./components/layout/Layout"
import ErrorBoundary from "./components/shared/ErrorBoundary"
import NotFound from "./pages/NotFound"
import { useAuth } from "./hooks/useAuth"

// Eagerly loaded — needed before auth check on every page visit
import LandingPage from "./pages/Landing/LandingPage"

// Lazy-loaded auth pages — only needed when unauthenticated
const LoginPage = lazy(() => import("./pages/Login/LoginPage"))
const SignupPage = lazy(() => import("./pages/Signup/SignupPage"))
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPassword/ForgotPasswordPage"))
const ResetPasswordPage = lazy(() => import("./pages/ResetPassword/ResetPasswordPage"))
const EmailVerificationPage = lazy(() => import("./pages/EmailVerification/EmailVerificationPage"))

// Lazy-loaded app pages — only needed when authenticated
const DashboardPage = lazy(() => import("./pages/Dashboard/DashboardPage"))
const AuditLogPage = lazy(() => import("./pages/AuditLog/AuditLogPage"))
const PoliciesPage = lazy(() => import("./pages/Policies/PoliciesPage"))
const SettingsPage = lazy(() => import("./pages/Settings/SettingsPage"))
const IntegrationPage = lazy(() => import("./pages/Integration/IntegrationPage"))
const AccountPage = lazy(() => import("./pages/Account/AccountPage"))
const TestLabPage = lazy(() => import("./pages/TestLab/TestLabPage"))

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
      <Suspense fallback={<div className="h-full bg-dashboard-bg" />}>
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
            path="/verify-email"
            element={
              <PublicRoute>
                <EmailVerificationPage />
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
            <Route path="/test-lab" element={<TestLabPage />} />
            <Route path="/policies" element={<PoliciesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/integration" element={<IntegrationPage />} />
            <Route path="/account" element={<AccountPage />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
