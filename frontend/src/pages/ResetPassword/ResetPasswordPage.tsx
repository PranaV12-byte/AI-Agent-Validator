import { ShieldCheck } from "lucide-react"
import type { FormEvent } from "react"
import { useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"

import { confirmPasswordReset } from "../../services/authService"

function ResetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""

  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const passwordMismatch =
    newPassword.length > 0 &&
    confirmPassword.length > 0 &&
    newPassword !== confirmPassword

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    if (!token) {
      setError("Reset link is invalid. Please request a new one.")
      return
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsSubmitting(true)

    try {
      await confirmPasswordReset(token, newPassword)
      navigate("/login?reset=1")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(
        typeof detail === "string"
          ? detail
          : "Could not reset password. The link may have expired.",
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!token) {
    return (
      <div className="h-full bg-dashboard-bg text-white flex items-center justify-center p-6">
        <div className="w-full max-w-md bg-card-bg border border-border-color rounded-2xl p-8 text-center space-y-4">
          <p className="text-brand-red">Invalid reset link.</p>
          <button
            onClick={() => navigate("/forgot-password")}
            className="text-brand-green underline text-sm"
          >
            Request a new reset link
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full bg-dashboard-bg text-white flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-card-bg border border-border-color rounded-2xl p-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-brand-green/20 rounded-lg flex items-center justify-center border border-brand-green/30">
            <ShieldCheck className="w-6 h-6 text-brand-green" />
          </div>
          <div>
            <p className="text-xl font-bold tracking-tight">Safebot</p>
            <p className="text-text-muted text-sm">Choose a new password</p>
          </div>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label
              htmlFor="reset-new-password"
              className="block text-sm text-text-muted mb-2"
            >
              New password
            </label>
            <input
              id="reset-new-password"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              required
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
            />
          </div>

          <div>
            <label
              htmlFor="reset-confirm-password"
              className="block text-sm text-text-muted mb-2"
            >
              Confirm new password
            </label>
            <input
              id="reset-confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              className={`w-full bg-dashboard-bg border rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:outline-none ${
                passwordMismatch
                  ? "border-brand-red focus:ring-brand-red"
                  : "border-border-color focus:ring-brand-green"
              }`}
            />
            {passwordMismatch ? (
              <p className="text-xs text-brand-red mt-1">
                Passwords do not match.
              </p>
            ) : null}
          </div>

          {error ? (
            <div className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
              <span>{error}</span>
              {error.toLowerCase().includes("expired") ||
              error.toLowerCase().includes("invalid") ? (
                <button
                  type="button"
                  onClick={() => navigate("/forgot-password")}
                  className="ml-1 underline text-brand-green"
                >
                  Request a new link →
                </button>
              ) : null}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting || passwordMismatch}
            className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Updating password..." : "Update password"}
          </button>
        </form>
      </div>
    </div>
  )
}

export default ResetPasswordPage
