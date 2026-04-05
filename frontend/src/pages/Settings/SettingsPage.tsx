import { useEffect, useMemo, useState, type FormEvent } from "react"
import { toast } from "sonner"

import { useAuth } from "../../hooks/useAuth"
import { changePasswordRequest, regenerateApiKeyRequest } from "../../services/authService"
import { fetchSafetyConfig, updateSafetyConfig } from "../../services/dashboardService"
import type { SafetyConfig } from "../../types/api"
import DeveloperSettingsCard from "./components/DeveloperSettingsCard"
import SaveSettingsButton from "./components/SaveSettingsButton"
import SecurityPostureCard, { type SecurityPostureForm } from "./components/SecurityPostureCard"

function toForm(config: SafetyConfig): SecurityPostureForm {
  return {
    global_block_enabled: config.global_block_enabled,
    pii_redaction: config.pii_redaction,
    fallback_message: config.fallback_message,
    log_retention_days: config.log_retention_days,
  }
}

function ChangePasswordCard() {
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = newPassword.length > 0 && confirmPassword.length > 0 && newPassword !== confirmPassword

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }
    if (!/[A-Za-z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      setError("Password must contain at least one letter and one number.")
      return
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setIsSubmitting(true)
    try {
      await changePasswordRequest(currentPassword, newPassword)
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
      toast.success("Password updated")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === "string" ? detail : "Could not update password. Please try again.")
      toast.error("Could not update password")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
      <h2 className="text-lg font-semibold">Change Password</h2>
      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
        <div>
          <label htmlFor="current-password" className="block text-sm text-text-muted mb-1">
            Current password
          </label>
          <input
            id="current-password"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>
        <div>
          <label htmlFor="new-password" className="block text-sm text-text-muted mb-1">
            New password
          </label>
          <input
            id="new-password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>
        <div>
          <label htmlFor="confirm-new-password" className="block text-sm text-text-muted mb-1">
            Confirm new password
          </label>
          <input
            id="confirm-new-password"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-4 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
          {mismatch ? (
            <p className="text-sm text-brand-red mt-1">Passwords do not match.</p>
          ) : null}
        </div>
        {error ? (
          <p className="text-sm text-brand-red">{error}</p>
        ) : null}
        <button
          type="submit"
          disabled={isSubmitting || mismatch}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSubmitting ? "Updating..." : "Update password"}
        </button>
      </form>
    </section>
  )
}

function SettingsPage() {
  const { user, refreshProfile } = useAuth()

  const [newApiKey, setNewApiKey] = useState<string | null>(null)
  const [isRotating, setIsRotating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [config, setConfig] = useState<SafetyConfig | null>(null)
  const [form, setForm] = useState<SecurityPostureForm>({
    global_block_enabled: false,
    pii_redaction: true,
    fallback_message: "",
    log_retention_days: 30,
  })
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const nextConfig = await fetchSafetyConfig()
        if (!cancelled) {
          setConfig(nextConfig)
          setForm(toForm(nextConfig))
        }
      } catch {
        if (!cancelled) {
          setError("Could not load safety settings.")
          toast.error("Could not load safety settings")
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [])

  const hasUnsavedChanges = useMemo(() => {
    if (!config) {
      return false
    }

    return JSON.stringify(form) !== JSON.stringify(toForm(config))
  }, [config, form])

  async function handleRotateApiKey() {
    setError(null)
    setIsRotating(true)

    try {
      const response = await regenerateApiKeyRequest()
      setNewApiKey(response.api_key)
      await refreshProfile()
    } catch {
      setError("Could not rotate API key. Please try again.")
      toast.error("Could not rotate API key")
    } finally {
      setIsRotating(false)
    }
  }

  async function handleCopyPrefix() {
    if (!user?.api_key_prefix) {
      return
    }

    await navigator.clipboard.writeText(user.api_key_prefix)
    toast.success("API key prefix copied")
  }

  async function handleCopyKey() {
    if (!newApiKey) {
      return
    }

    await navigator.clipboard.writeText(newApiKey)
    toast.success("API key copied")
  }

  async function handleSaveSettings() {
    if (!hasUnsavedChanges) {
      return
    }

    if (form.log_retention_days < 1) {
      setError("Log retention days must be at least 1.")
      toast.error("Log retention days must be at least 1")
      return
    }

    setError(null)
    setIsSaving(true)

    try {
      const updated = await updateSafetyConfig(form)
      setConfig(updated)
      setForm(toForm(updated))
      toast.success("Settings saved")
    } catch {
      setError("Could not save settings. Please try again.")
      toast.error("Could not save settings")
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">Settings</h1>
        <p className="text-text-muted">Control how Safebot protects your AI and manage your connection details.</p>
      </div>

      {error ? (
        <p className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
          {error}
        </p>
      ) : null}

      <SecurityPostureCard form={form} onChange={setForm} isLoading={config === null} />

      <DeveloperSettingsCard
        tenantId={user?.id ?? null}
        apiKeyPrefix={user?.api_key_prefix ?? null}
        newApiKey={newApiKey}
        isRotating={isRotating}
        onRotate={handleRotateApiKey}
        onCopyPrefix={handleCopyPrefix}
        onCopyNewKey={handleCopyKey}
      />

      <ChangePasswordCard />

      <SaveSettingsButton
        disabled={!hasUnsavedChanges}
        isSaving={isSaving}
        hasUnsavedChanges={hasUnsavedChanges}
        onClick={handleSaveSettings}
      />
    </section>
  )
}

export default SettingsPage
