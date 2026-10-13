type SecurityPostureForm = {
  global_block_enabled: boolean
  injection_protection: boolean
  pii_redaction: boolean
  fail_mode: "open" | "closed"
  fallback_message: string
  log_retention_days: number
}

type SecurityPostureCardProps = {
  form: SecurityPostureForm
  onChange: (next: SecurityPostureForm) => void
  isLoading?: boolean
}

function SecurityPostureCard({ form, onChange, isLoading = false }: SecurityPostureCardProps) {
  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-5">
      <h2 className="text-lg font-semibold">Protection Settings</h2>

      <label className="flex items-center justify-between">
        <div>
          <span className="text-sm text-text-muted">Pause all AI requests</span>
          <p className="text-xs text-text-muted/70 mt-0.5">
            Stops every request, including harmless messages. Turn off to resume.
          </p>
        </div>
        <input
          aria-label="Pause all AI requests"
          type="checkbox"
          checked={form.global_block_enabled}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, global_block_enabled: e.target.checked })}
        />
      </label>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Block AI manipulation attempts</span>
        <input
          aria-label="Block AI manipulation attempts"
          type="checkbox"
          checked={form.injection_protection}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, injection_protection: e.target.checked })}
        />
      </label>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Hide personal info in messages</span>
        <input
          aria-label="Hide personal info in messages"
          type="checkbox"
          checked={form.pii_redaction}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, pii_redaction: e.target.checked })}
        />
      </label>

      <div>
        <label htmlFor="fail-mode-settings" className="block text-sm text-text-muted mb-2">
          If something goes wrong
        </label>
        <select
          id="fail-mode-settings"
          aria-label="If something goes wrong"
          value={form.fail_mode}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, fail_mode: e.target.value as "open" | "closed" })}
          className="bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option value="closed">Block the message (safe)</option>
          <option value="open">Allow the message (risky)</option>
        </select>
      </div>

      <div>
        <label htmlFor="fallback-message" className="block text-sm text-text-muted mb-2">
          Message shown when AI is blocked
        </label>
        <input
          id="fallback-message"
          value={form.fallback_message}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, fallback_message: e.target.value })}
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <p className="text-xs text-text-muted mt-1">This is what your customer sees when a message is stopped.</p>
      </div>

      <div>
        <label htmlFor="retention-days" className="block text-sm text-text-muted mb-2">
          Keep activity records for (days)
        </label>
        <input
          id="retention-days"
          type="number"
          min={1}
          value={form.log_retention_days}
          disabled={isLoading}
          onChange={(e) => onChange({ ...form, log_retention_days: Number(e.target.value) || 0 })}
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </div>
    </section>
  )
}

export type { SecurityPostureForm }
export default SecurityPostureCard
