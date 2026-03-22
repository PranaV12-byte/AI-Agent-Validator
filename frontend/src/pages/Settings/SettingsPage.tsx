import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { useAuth } from "../../hooks/useAuth"
import { regenerateApiKeyRequest } from "../../services/authService"
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
        <p className="text-text-muted">Manage global security posture and developer access.</p>
      </div>

      {error ? (
        <p className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
          {error}
        </p>
      ) : null}

      <SecurityPostureCard form={form} onChange={setForm} />

      <DeveloperSettingsCard
        tenantId={user?.id ?? null}
        apiKeyPrefix={user?.api_key_prefix ?? null}
        newApiKey={newApiKey}
        isRotating={isRotating}
        onRotate={handleRotateApiKey}
        onCopyPrefix={handleCopyPrefix}
        onCopyNewKey={handleCopyKey}
      />

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
