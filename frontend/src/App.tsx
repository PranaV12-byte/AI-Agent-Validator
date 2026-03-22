import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "sonner"

import ProtectedRoute from "./components/auth/ProtectedRoute"
import PublicRoute from "./components/auth/PublicRoute"
import Layout from "./components/layout/Layout"
import NotFound from "./pages/NotFound"
import AuditLogPage from "./pages/AuditLog/AuditLogPage"
import DashboardPage from "./pages/Dashboard/DashboardPage"
import LoginPage from "./pages/Login/LoginPage"
import PoliciesPage from "./pages/Policies/PoliciesPage"
import SettingsPage from "./pages/Settings/SettingsPage"
import IntegrationPage from "./pages/Integration/IntegrationPage"

function App() {
  return (
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
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/login"
          element={
            <PublicRoute>
              <LoginPage />
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
  )
}

export default App
