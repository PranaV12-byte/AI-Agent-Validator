import { ShieldCheck } from "lucide-react"
import type { FormEvent } from "react"
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { apiClient } from "../../services/apiClient"

function SignupPage() {
  const navigate = useNavigate()
  const [companyName, setCompanyName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [emailExists, setEmailExists] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setEmailExists(false)

    if (password.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }

    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
      setError("Password must contain at least one letter and one number.")
      return
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsSubmitting(true)

    try {
      await apiClient.post("/auth/signup", {
        company_name: companyName,
        email,
        password,
      })
      toast.success("Account created! Please sign in.")
      setTimeout(() => navigate("/login?signup=1"), 1500)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (typeof detail === "string" && detail.toLowerCase().includes("already registered")) {
        setEmailExists(true)
        setError("An account with this email already exists.")
      } else {
        setError(typeof detail === "string" ? detail : "Could not sign up. Please try again.")
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const passwordMismatch =
    password.length > 0 && confirmPassword.length > 0 && password !== confirmPassword

  return (
    <div className="h-full bg-dashboard-bg text-white flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-card-bg border border-border-color rounded-2xl p-8">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-brand-green/20 rounded-lg flex items-center justify-center border border-brand-green/30">
            <ShieldCheck className="w-6 h-6 text-brand-green" />
          </div>
          <div>
            <p className="text-xl font-bold tracking-tight">Safebot</p>
            <p className="text-text-muted text-sm">Create your account</p>
          </div>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="signup-company" className="block text-sm text-text-muted mb-2">
              Company name
            </label>
            <input
              id="signup-company"
              value={companyName}
              onChange={(event) => setCompanyName(event.target.value)}
              required
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="signup-email" className="block text-sm text-text-muted mb-2">
              Email
            </label>
            <input
              id="signup-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="signup-password" className="block text-sm text-text-muted mb-2">
              Password
            </label>
            <input
              id="signup-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="signup-confirm-password" className="block text-sm text-text-muted mb-2">
              Confirm password
            </label>
            <input
              id="signup-confirm-password"
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
              <p className="text-xs text-brand-red mt-1">Passwords do not match.</p>
            ) : null}
          </div>

          {error ? (
            <div className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
              <span>{error}</span>
              {emailExists ? (
                <button
                  type="button"
                  onClick={() => navigate("/login")}
                  className="ml-1 underline text-brand-green"
                >
                  Sign in instead →
                </button>
              ) : null}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting || passwordMismatch}
            className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-text-muted">
          Already have an account?{" "}
          <button
            onClick={() => navigate("/login")}
            className="text-brand-green hover:underline cursor-pointer"
          >
            Sign in
          </button>
        </div>
      </div>
    </div>
  )
}

export default SignupPage
