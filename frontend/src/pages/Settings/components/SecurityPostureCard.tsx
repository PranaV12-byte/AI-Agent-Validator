type SecurityPostureForm = {
  global_block_enabled: boolean
  pii_redaction: boolean
  fallback_message: string
  log_retention_days: number
}

type SecurityPostureCardProps = {
  form: SecurityPostureForm
  onChange: (next: SecurityPostureForm) => void
}

function SecurityPostureCard({ form, onChange }: SecurityPostureCardProps) {
  return (
    <section className="border border-border-color rounded-xl p-5 bg-dashboard-bg/40 space-y-5">
      <h2 className="text-lg font-semibold">Security Posture</h2>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Global Block Enabled</span>
        <input
          type="checkbox"
          checked={form.global_block_enabled}
          onChange={(event) =>
            onChange({ ...form, global_block_enabled: event.target.checked })
          }
        />
      </label>

      <label className="flex items-center justify-between">
        <span className="text-sm text-text-muted">Redact PII Enabled</span>
        <input
          type="checkbox"
          checked={form.pii_redaction}
          onChange={(event) => onChange({ ...form, pii_redaction: event.target.checked })}
        />
      </label>

      <div>
        <label htmlFor="fallback-message" className="block text-sm text-text-muted mb-2">
          Default Block Message
        </label>
        <input
          id="fallback-message"
          value={form.fallback_message}
          onChange={(event) => onChange({ ...form, fallback_message: event.target.value })}
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
        />
      </div>

      <div>
        <label htmlFor="retention-days" className="block text-sm text-text-muted mb-2">
          Log Retention Days
        </label>
        <input
          id="retention-days"
          type="number"
          min={1}
          value={form.log_retention_days}
          onChange={(event) =>
            onChange({ ...form, log_retention_days: Number(event.target.value) || 0 })
          }
          className="w-full bg-card-bg border border-border-color rounded-lg px-3 py-2.5 text-sm"
        />
      </div>
    </section>
  )
}

export type { SecurityPostureForm }
export default SecurityPostureCard
