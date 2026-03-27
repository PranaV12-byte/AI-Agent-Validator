import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import {
  fetchPolicyConfig,
  updatePolicyConfig,
} from "../../services/policyConfigService"
import type { PolicyConfig } from "../../types/api"

function PolicyPage() {
  const [config, setConfig] = useState<PolicyConfig | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isDeploying, setIsDeploying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [injectionProtection, setInjectionProtection] = useState(true)
  const [piiRedaction, setPiiRedaction] = useState(true)
  const [failMode, setFailMode] = useState<"open" | "closed">("closed")

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)

      try {
        const response = await fetchPolicyConfig()
        if (!cancelled) {
          setConfig(response)
          setInjectionProtection(response.injection_protection)
          setPiiRedaction(response.pii_redaction)
          setFailMode(response.fail_mode)
        }
      } catch {
        if (!cancelled) {
          setError("Could not load policy config")
          toast.error("Could not load policy config")
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void load()

    return () => {
      cancelled = true
    }
  }, [])

  const hasChanges = useMemo(() => {
    if (!config) {
      return false
    }

    return (
      config.injection_protection !== injectionProtection ||
      config.pii_redaction !== piiRedaction ||
      config.fail_mode !== failMode
    )
  }, [config, failMode, injectionProtection, piiRedaction])

  async function handleDeploy() {
    if (!hasChanges) {
      return
    }

    setIsDeploying(true)
    setError(null)

    try {
      const updated = await updatePolicyConfig({
        injection_protection: injectionProtection,
        pii_redaction: piiRedaction,
        fail_mode: failMode,
      })
      setConfig(updated)
      toast.success(`Policy deployment v${updated.active_policy_version}.0 successful`)
    } catch {
      setError("Deployment failed")
      toast.error("Deployment failed")
    } finally {
      setIsDeploying(false)
    }
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Protection Settings</h1>
        <p className="text-text-muted mt-1">
          Last updated: version {config?.active_policy_version ?? 0}.0
        </p>
      </div>

      {error ? (
        <p className="text-sm text-brand-red bg-brand-red/10 border border-brand-red/30 rounded-lg px-3 py-2">
          {error}
        </p>
      ) : null}

      <div className="bg-card-bg border border-border-color rounded-2xl p-6 space-y-5">
        {isLoading ? (
          <div className="space-y-3">
            <div className="h-4 w-56 bg-border-color/70 rounded animate-pulse" />
            <div className="h-4 w-40 bg-border-color/70 rounded animate-pulse" />
            <div className="h-4 w-48 bg-border-color/70 rounded animate-pulse" />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm text-text-muted">Block AI manipulation attempts</span>
                <p className="text-xs text-text-muted/70 mt-0.5">Stops people from tricking your AI into ignoring its rules.</p>
              </div>
              <input
                aria-label="Block AI manipulation attempts"
                type="checkbox"
                checked={injectionProtection}
                onChange={(event) => setInjectionProtection(event.target.checked)}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm text-text-muted">Hide personal info automatically</span>
                <p className="text-xs text-text-muted/70 mt-0.5">Removes names, emails, and phone numbers from messages.</p>
              </div>
              <input
                aria-label="Hide personal info automatically"
                type="checkbox"
                checked={piiRedaction}
                onChange={(event) => setPiiRedaction(event.target.checked)}
              />
            </div>

            <div>
              <label htmlFor="fail-mode" className="block text-sm text-text-muted mb-2">
                If something goes wrong
              </label>
              <select
                id="fail-mode"
                aria-label="If something goes wrong"
                value={failMode}
                onChange={(event) => setFailMode(event.target.value as "open" | "closed")}
                className="bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
              >
                <option value="closed">Block the message (safe)</option>
                <option value="open">Allow the message (risky)</option>
              </select>
            </div>
          </>
        )}
      </div>

      <button
        type="button"
        data-testid="deploy-changes-button"
        onClick={() => void handleDeploy()}
        disabled={isDeploying || !hasChanges}
        className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-5 py-3 font-medium hover:bg-brand-green/20 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isDeploying ? "Saving..." : "Save & Apply Changes"}
      </button>
    </section>
  )
}

export default PolicyPage
