import { Eye, EyeOff, ShieldCheck } from "lucide-react"
import type { FormEvent } from "react"
import { useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"

import { useAuth } from "../../hooks/useAuth"
import { getErrorMessage } from "../../services/apiClient"

function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const redirectUri = useMemo(() => {
    const value = searchParams.get("redirect_uri")
    return value && value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard"
  }, [searchParams])

  const justSignedUp = searchParams.get("signup") === "1"
  const justReset = searchParams.get("reset") === "1"
  const justLoggedOut = searchParams.get("logout") === "1"

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      await login({ email, password })
      navigate(redirectUri, { replace: true })
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Invalid email or password."))
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
            <p className="text-text-muted text-sm">Sign in to continue</p>
          </div>
        </div>

        {justSignedUp ? (
          <p className="text-sm text-brand-green bg-brand-green/10 border border-brand-green/30 rounded-lg px-3 py-2 mb-6">
            Account created! Please sign in to continue.
          </p>
        ) : null}

        {justReset ? (
          <p className="text-sm text-brand-green bg-brand-green/10 border border-brand-green/30 rounded-lg px-3 py-2 mb-6">
            Password updated! Sign in with your new password.
          </p>
        ) : null}

        {justLoggedOut ? (
          <p className="text-sm text-brand-green bg-brand-green/10 border border-brand-green/30 rounded-lg px-3 py-2 mb-6">
            Signed out successfully. See you next time!
          </p>
        ) : null}

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="email" className="block text-sm text-text-muted mb-2">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label htmlFor="password" className="block text-sm text-text-muted">
                Password
              </label>
              <button
                type="button"
                onClick={() => navigate("/forgot-password")}
                className="text-xs text-brand-green hover:underline cursor-pointer"
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm pr-10 focus:ring-1 focus:ring-brand-green focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-white"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error ? (
            <div className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
              <span>{error}</span>
              {error.toLowerCase().includes("not verified") ? (
                <button
                  type="button"
                  onClick={() => navigate("/verify-email")}
                  className="ml-1 underline text-brand-green"
                >
                  Resend verification link →
                </button>
              ) : null}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-text-muted">
          Need an account?{" "}
          <button
            onClick={() => navigate("/signup")}
            className="text-brand-green hover:underline cursor-pointer"
          >
            Sign up here
          </button>
        </div>
      </div>
    </div>
  )
}

export default LoginPage
