type SecurityPostureForm = {
  global_block_enabled: boolean
  pii_redaction: boolean
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
        <span className="text-sm text-text-muted">Block all harmful messages</span>
        <input
          type="checkbox"
          checked={form.global_block_enabled}
          disabled={isLoading}
          onChange={(event) =>
            onChange({ ...form, global_block_enabled: event.target.checked })
          }
        />
      </label>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Hide personal info in messages</span>
        <input
          type="checkbox"
          checked={form.pii_redaction}
          disabled={isLoading}
          onChange={(event) => onChange({ ...form, pii_redaction: event.target.checked })}
        />
      </label>

      <div>
        <label htmlFor="fallback-message" className="block text-sm text-text-muted mb-2">
          Message shown when AI is blocked
        </label>
        <input
          id="fallback-message"
          value={form.fallback_message}
          disabled={isLoading}
          onChange={(event) => onChange({ ...form, fallback_message: event.target.value })}
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
          onChange={(event) =>
            onChange({ ...form, log_retention_days: Number(event.target.value) || 0 })
          }
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        />
      </div>
    </section>
  )
}

export type { SecurityPostureForm }
export default SecurityPostureCard
