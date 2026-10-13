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
  if (log.action === "ERROR") return log.violation_type ?? "Request could not be completed"
  return "Request allowed by guardrails"
}

function actionLabel(action: AuditLog["action"]): string {
  return action === "ERROR" ? "ERROR" : action.toLowerCase()
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString()
}

function getAnchoringStatus(log: AuditLog): NonNullable<AuditLog["anchoring_status"]> {
  const transactionId = log.algorand_tx_id
  if (transactionId?.toLowerCase().startsWith("mock_tx_")) {
    return "not_anchored"
  }
  if (log.anchoring_status === "anchored" && !transactionId) {
    return "pending"
  }
  if (log.anchoring_status) {
    return log.anchoring_status
  }
  return transactionId ? "anchored" : "pending"
}

function anchoringLabel(status: NonNullable<AuditLog["anchoring_status"]>): string {
  switch (status) {
    case "anchored": return "Anchored"
    case "pending": return "Pending"
    case "disabled": return "Disabled for this local demo"
    case "not_anchored": return "Not anchored"
  }
}

function hashProvenanceLabel(log: AuditLog): string {
  if (log.payload_hash_provenance === "stored_unverified") {
    return "Stored hash; not independently verified"
  }
  if (log.payload_hash_provenance === "unavailable" || !log.payload_hash) {
    return "Unavailable"
  }
  return "Stored hash; provenance not supplied"
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
        <Field label="Action">
          <span className={`uppercase ${log.action === "ERROR" ? "font-bold text-brand-red" : ""}`}>
            {actionLabel(log.action)}
          </span>
        </Field>
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
        <Field label="Algorand anchoring">
          {getAnchoringStatus(log) === "anchored" && log.algorand_tx_id ? (
            <a
              href={`https://testnet.explorer.perawallet.app/tx/${log.algorand_tx_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-brand-green hover:underline font-mono text-xs"
            >
              {log.algorand_tx_id}
            </a>
          ) : (
            anchoringLabel(getAnchoringStatus(log))
          )}
        </Field>
        <Field label="Hash provenance">{hashProvenanceLabel(log)}</Field>
        {log.payload_hash ? (
          <Field label="Payload hash">
            <code className="block break-all text-xs">{log.payload_hash}</code>
          </Field>
        ) : null}
        {log.redacted_fields?.length ? (
          <Field label="Display sanitization">
            <span>
              Stored history is unchanged. Displayed values were sanitized in: {log.redacted_fields.join(", ")}.
              The hash remains stored as-is and has not been independently verified.
            </span>
          </Field>
        ) : null}

        <div>
          <p className="text-text-muted mb-1">Sanitized Input Preview</p>
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
