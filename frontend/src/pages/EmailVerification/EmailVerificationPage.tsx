import { ShieldCheck } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"

import { resendVerification, verifyEmail } from "../../services/authService"

type VerifyState = "loading" | "success" | "already_verified" | "error" | "no_token"

function getVerificationToken(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    return new URL(url, window.location.origin).searchParams.get("token")
  } catch {
    return null
  }
}

function EmailVerificationPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get("token") ?? ""

  const [state, setState] = useState<VerifyState>(token ? "loading" : "no_token")
  const [resendEmail, setResendEmail] = useState("")
  const [resendSubmitted, setResendSubmitted] = useState(false)
  const [resendLoading, setResendLoading] = useState(false)
  const [resendError, setResendError] = useState<string | null>(null)
  const verificationRequestRef = useRef<{
    token: string
    promise: Promise<{ message: string }>
  } | null>(null)

  useEffect(() => {
    if (!token) {
      setState("no_token")
      return
    }

    let cancelled = false
    setState("loading")

    // StrictMode replays effects during development. Verification tokens are
    // single-use, so both effect lifecycles for the same token must share the
    // same in-flight request rather than consuming it twice.
    if (verificationRequestRef.current?.token !== token) {
      verificationRequestRef.current = { token, promise: verifyEmail(token) }
    }
    const verificationPromise = verificationRequestRef.current.promise

    async function verify() {
      try {
        const data = await verificationPromise
        if (cancelled) return
        if (data.message.toLowerCase().includes("already")) {
          setState("already_verified")
        } else {
          setState("success")
        }
      } catch {
        if (!cancelled) setState("error")
      }
    }

    void verify()
    return () => { cancelled = true }
  }, [token])

  async function handleResend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setResendError(null)
    setResendLoading(true)
    try {
      const response = await resendVerification(resendEmail)
      const verificationToken = getVerificationToken(response.verification_url)
      if (verificationToken) {
        navigate(`/verify-email?token=${encodeURIComponent(verificationToken)}`, {
          replace: true,
        })
      } else {
        setResendSubmitted(true)
      }
    } catch {
      setResendError("Something went wrong. Please try again.")
    } finally {
      setResendLoading(false)
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
            <p className="text-text-muted text-sm">Email verification</p>
          </div>
        </div>

        {state === "loading" && (
          <p role="status" aria-live="polite" className="text-text-muted text-sm">
            Verifying your email address…
          </p>
        )}

        {(state === "success" || state === "already_verified") && (
          <div className="space-y-4">
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-brand-green bg-brand-green/10 border border-brand-green/30 rounded-lg px-3 py-2"
            >
              {state === "success"
                ? "Your email has been verified! You can now sign in."
                : "Your email is already verified. You can sign in."}
            </p>
            <button
              onClick={() => navigate("/login")}
              className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors text-sm"
            >
              Go to sign in
            </button>
          </div>
        )}

        {(state === "error" || state === "no_token") && (
          <div className="space-y-5">
            <p
              role="alert"
              className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2"
            >
              {state === "no_token"
                ? "No verification token found in the link."
                : "This verification link is invalid or has expired."}
            </p>

            {resendSubmitted ? (
              <p className="text-sm text-text-muted">
                If that email is registered and unverified, a new link has been sent.
              </p>
            ) : (
              <form className="space-y-4" onSubmit={handleResend}>
                <p className="text-sm text-text-muted">Request a new verification link:</p>
                <div>
                  <label htmlFor="resend-email" className="block text-sm text-text-muted mb-2">
                    Email address
                  </label>
                  <input
                    id="resend-email"
                    type="email"
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    required
                    className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
                  />
                </div>
                {resendError ? (
                  <p className="text-sm text-brand-red">{resendError}</p>
                ) : null}
                <button
                  type="submit"
                  disabled={resendLoading}
                  className="w-full rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2.5 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed text-sm"
                >
                  {resendLoading ? "Sending…" : "Resend verification link"}
                </button>
              </form>
            )}

            <div className="text-center">
              <button
                type="button"
                onClick={() => navigate("/login")}
                className="text-sm text-brand-green hover:underline cursor-pointer"
              >
                Back to sign in
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default EmailVerificationPage
