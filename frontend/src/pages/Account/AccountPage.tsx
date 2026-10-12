import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { useAuth } from "../../hooks/useAuth"
import { updateProfileRequest } from "../../services/authService"

function getVerificationToken(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    return new URL(url, window.location.origin).searchParams.get("token")
  } catch {
    return null
  }
}

function AccountPage() {
  const { user, logout, refreshProfile } = useAuth()
  const navigate = useNavigate()

  const [companyName, setCompanyName] = useState(user?.company_name ?? "")
  const [email, setEmail] = useState(user?.email ?? "")
  const [isSavingName, setIsSavingName] = useState(false)
  const [isSavingEmail, setIsSavingEmail] = useState(false)
  const [nameError, setNameError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)

  const nameChanged = companyName.trim() !== (user?.company_name ?? "")
  const emailChanged = email.trim() !== (user?.email ?? "")

  async function handleSaveName() {
    if (!nameChanged || !companyName.trim()) return
    setNameError(null)
    setIsSavingName(true)
    try {
      await updateProfileRequest({ company_name: companyName.trim() })
      await refreshProfile()
      toast.success("Company name updated")
    } catch {
      setNameError("Could not update company name. Please try again.")
      toast.error("Could not update company name")
    } finally {
      setIsSavingName(false)
    }
  }

  async function handleSaveEmail() {
    if (!emailChanged || !email.trim()) return
    setEmailError(null)
    setIsSavingEmail(true)
    try {
      const updated = await updateProfileRequest({ email: email.trim() })
      const verificationToken = getVerificationToken(updated.verification_url)

      if (verificationToken) {
        navigate(`/verify-email?token=${encodeURIComponent(verificationToken)}`, {
          replace: true,
        })
      } else {
        navigate("/login?verification=pending", { replace: true })
      }
      // Email changes invalidate the current auth_version. Do not refresh the
      // now-revoked profile token; preserve the public handoff route above.
      logout()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setEmailError(typeof detail === "string" ? detail : "Could not update email. Please try again.")
      toast.error("Could not update email")
    } finally {
      setIsSavingEmail(false)
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Account</h1>
        <p className="text-text-muted">Manage your account details.</p>
      </div>

      <div className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
        <h2 className="text-lg font-semibold">Company Name</h2>
        <div>
          <label htmlFor="account-company-name" className="block text-sm text-text-muted mb-2">
            Company name
          </label>
          <input
            id="account-company-name"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>
        {nameError ? <p className="text-sm text-brand-red">{nameError}</p> : null}
        <button
          type="button"
          onClick={() => void handleSaveName()}
          disabled={isSavingName || !nameChanged}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSavingName ? "Saving..." : "Save"}
        </button>
      </div>

      <div className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
        <h2 className="text-lg font-semibold">Email Address</h2>
        <div className="bg-brand-green/5 border border-brand-green/20 rounded-lg px-3 py-2 text-xs text-text-muted">
          Changing your email will require re-verification before you can sign in again.
        </div>
        <div>
          <label htmlFor="account-email" className="block text-sm text-text-muted mb-2">
            Email address
          </label>
          <input
            id="account-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
          />
        </div>
        {emailError ? <p className="text-sm text-brand-red">{emailError}</p> : null}
        <button
          type="button"
          onClick={() => void handleSaveEmail()}
          disabled={isSavingEmail || !emailChanged}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSavingEmail ? "Saving..." : "Update email"}
        </button>
      </div>
    </section>
  )
}

export default AccountPage
