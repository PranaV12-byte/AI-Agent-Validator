import { useState, useEffect } from "react"

type DeveloperSettingsCardProps = {
  tenantId: string | null
  apiKeyPrefix: string | null
  newApiKey: string | null
  isRotating: boolean
  onRotate: () => Promise<void>
  onCopyPrefix: () => Promise<void>
  onCopyNewKey: () => Promise<void>
}

function DeveloperSettingsCard({
  tenantId,
  apiKeyPrefix,
  newApiKey,
  isRotating,
  onRotate,
  onCopyPrefix,
  onCopyNewKey,
}: DeveloperSettingsCardProps) {
  const [showKey, setShowKey] = useState(false)
  const [confirming, setConfirming] = useState(false)
  useEffect(() => { setShowKey(false) }, [newApiKey])

  function handleRotateClick() {
    setConfirming(true)
  }

  async function handleConfirmRotate() {
    setConfirming(false)
    await onRotate()
  }

  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
      <h2 className="text-lg font-semibold">Developer Settings</h2>

      <p className="text-sm text-text-muted break-all">
        Your account ID: <span className="text-white">{tenantId ?? "--"}</span>
      </p>

      <div className="flex items-center gap-3 flex-wrap">
        <p className="text-sm text-text-muted">
          API key prefix: <span className="text-white">{apiKeyPrefix ?? "--"}</span>
        </p>
        <button
          type="button"
          onClick={() => void onCopyPrefix()}
          className="text-sm text-text-muted hover:text-white"
        >
          Copy Prefix
        </button>
      </div>

      {confirming ? (
        <div className="space-y-3">
          <p className="text-sm text-brand-red">
            This will break existing integrations. Your old key will stop working immediately.
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void handleConfirmRotate()}
              disabled={isRotating}
              className="rounded-lg bg-brand-red/10 border border-brand-red/30 text-brand-red px-4 py-2 font-medium hover:bg-brand-red/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isRotating ? "Rotating..." : "Yes, rotate key"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-lg border border-border-color text-text-muted px-4 py-2 font-medium hover:text-white hover:bg-white/5 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleRotateClick}
          disabled={isRotating}
          className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isRotating ? "Rotating..." : "Regenerate API Key"}
        </button>
      )}

      {newApiKey ? (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wide text-text-muted">
            New API key (copy now — it won't be shown again)
          </p>
          <div className="bg-card-bg border border-border-color rounded-lg p-3 text-sm font-mono break-all select-none">
            {showKey ? newApiKey : `${newApiKey.slice(0, 8)}${"*".repeat(24)}`}
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void onCopyNewKey()}
              className="text-sm text-text-muted hover:text-white"
            >
              Copy key
            </button>
            <button
              type="button"
              onClick={() => setShowKey((prev) => !prev)}
              className="text-sm text-text-muted hover:text-white"
            >
              {showKey ? "Hide" : "Reveal"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}

export default DeveloperSettingsCard
