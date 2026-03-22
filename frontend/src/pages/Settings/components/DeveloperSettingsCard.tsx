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
  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-4">
      <h2 className="text-lg font-semibold">Developer Settings</h2>

      <p className="text-sm text-text-muted break-all">
        Tenant ID: <span className="text-white">{tenantId ?? "--"}</span>
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

      <button
        type="button"
        onClick={() => void onRotate()}
        disabled={isRotating}
        className="rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-4 py-2 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {isRotating ? "Rotating..." : "Regenerate API Key"}
      </button>

      {newApiKey ? (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wide text-text-muted">New API key (copy now)</p>
          <div className="bg-card-bg border border-border-color rounded-lg p-3 text-sm font-mono break-all">
            {newApiKey}
          </div>
          <button
            type="button"
            onClick={() => void onCopyNewKey()}
            className="text-sm text-text-muted hover:text-white"
          >
            Copy key
          </button>
        </div>
      ) : null}
    </section>
  )
}

export default DeveloperSettingsCard
