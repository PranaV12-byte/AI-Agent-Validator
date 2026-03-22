import type { AuditLog } from "../../../types/api"

type AuditDetailDrawerProps = {
  log: AuditLog | null
  onClose: () => void
}

function inferReason(log: AuditLog): string {
  if (log.action === "BLOCKED") {
    return log.violation_type ?? "Blocked by policy"
  }
  if (log.action === "REDACTED") {
    return log.violation_type ?? "Sensitive data redacted"
  }
  return "Request allowed by guardrails"
}

function AuditDetailDrawer({ log, onClose }: AuditDetailDrawerProps) {
  if (!log) {
    return null
  }

  return (
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
        >
          Close
        </button>
      </div>

      <div className="space-y-5 text-sm">
        <div>
          <p className="text-text-muted mb-1">Action</p>
          <p className="font-medium uppercase">{log.action.toLowerCase()}</p>
        </div>

        <div>
          <p className="text-text-muted mb-1">Reason</p>
          <p className="font-medium">{inferReason(log)}</p>
        </div>

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
  )
}

export default AuditDetailDrawer
