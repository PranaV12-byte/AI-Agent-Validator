import { ShieldCheck } from "lucide-react"
import type { FormEvent } from "react"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { requestPasswordReset } from "../../services/authService"

function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [resetUrl, setResetUrl] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const data = await requestPasswordReset(email)
      setSubmitted(true)
      if (data.reset_url) {
        setResetUrl(data.reset_url)
      }
    } catch {
      setError("Something went wrong. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
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
            <p className="text-text-muted text-sm">Reset your password</p>
          </div>
        </div>

        {submitted ? (
          <div className="space-y-4">
            <p className="text-sm text-text-muted">
              If that email is registered you will receive a password-reset link
              shortly.
            </p>

            {import.meta.env.DEV && resetUrl ? (
              <div className="bg-brand-green/10 border border-brand-green/30 rounded-lg p-3 space-y-2">
                <p className="text-xs text-brand-green font-medium">
                  Dev mode — use this link to reset your password:
                </p>
                <a
                  href={resetUrl}
                  className="block text-xs text-brand-green underline break-all"
                >
                  {resetUrl}
                </a>
              </div>
            ) : null}

            <button
              onClick={() => navigate("/login")}
              className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors text-sm"
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="forgot-email" className="block text-sm text-text-muted mb-2">
                Email address
              </label>
              <input
                id="forgot-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
              />
            </div>

            {error ? (
              <p className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
                {error}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSubmitting ? "Sending..." : "Send reset link"}
            </button>

            <div className="text-center text-sm text-text-muted">
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="text-brand-green hover:underline cursor-pointer"
              >
                Back to sign in
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

export default ForgotPasswordPage
