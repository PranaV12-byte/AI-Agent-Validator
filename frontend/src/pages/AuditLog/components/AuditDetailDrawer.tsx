import { X } from "lucide-react"
import { useEffect } from "react"

import type { AuditLog } from "../../../types/api"

type AuditDetailDrawerProps = {
  log: AuditLog | null
  onClose: () => void
}

function inferReason(log: AuditLog): string {
  if (log.action === "BLOCKED") return log.violation_type ?? "Blocked by policy"
  if (log.action === "REDACTED") return log.violation_type ?? "Sensitive data redacted"
  return "Request allowed by guardrails"
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString()
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-text-muted mb-1">{label}</p>
      <div className="font-medium text-sm">{children}</div>
    </div>
  )
}

function AuditDetailDrawer({ log, onClose }: AuditDetailDrawerProps) {
  useEffect(() => {
    if (!log) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [log, onClose])

  if (!log) return null

  return (
    <>
      <div
        data-testid="drawer-backdrop"
        className="fixed inset-0 bg-black/40 z-30"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        data-testid={`audit-drawer-${log.id}`}
        className="fixed top-0 right-0 h-full w-full max-w-xl bg-sidebar-bg border-l border-border-color shadow-2xl z-40 p-6 overflow-y-auto"
      >
      <div className="flex items-start justify-between mb-6">
        <div>
          <h3 className="text-xl font-bold">Audit Detail</h3>
          <p className="text-xs text-text-muted mt-1 break-all">{log.id}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-text-muted hover:text-white transition-colors"
          aria-label="Close drawer"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-5 text-sm">
        <Field label="Timestamp">{formatTimestamp(log.created_at)}</Field>
        <Field label="Action"><span className="uppercase">{log.action.toLowerCase()}</span></Field>
        <Field label="Reason">{inferReason(log)}</Field>
        <Field label="Hook Type">{log.hook_type}</Field>
        <Field label="Severity">{log.severity}</Field>
        {log.processing_ms !== null ? (
          <Field label="Processing Time">{log.processing_ms}ms</Field>
        ) : null}
        {log.policy_version !== null ? (
          <Field label="Policy Version">{log.policy_version}</Field>
        ) : null}
        {log.session_id ? <Field label="Session ID">{log.session_id}</Field> : null}
        {log.ip_address ? <Field label="IP Address">{log.ip_address}</Field> : null}
        {log.algorand_tx_id ? (
          <Field label="Blockchain Record">
            <a
              href={`https://testnet.explorer.perawallet.app/tx/${log.algorand_tx_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-brand-green hover:underline font-mono text-xs"
            >
              {log.algorand_tx_id}
            </a>
          </Field>
        ) : null}

        <div>
          <p className="text-text-muted mb-1">Agent Input Payload</p>
          <pre className="bg-card-bg border border-border-color rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap break-all">
            {JSON.stringify({ input_preview: log.input_preview }, null, 2)}
          </pre>
        </div>

        <div>
          <p className="text-text-muted mb-1">Guardrail Decision Details</p>
          <pre className="bg-card-bg border border-border-color rounded-lg p-3 overflow-auto text-xs whitespace-pre-wrap break-all">
            {JSON.stringify(log.details, null, 2)}
          </pre>
        </div>
      </div>
    </aside>
    </>
  )
}

export default AuditDetailDrawer
