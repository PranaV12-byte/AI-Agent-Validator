import { ExternalLink } from "lucide-react"
import { FileSearch } from "lucide-react"

import type { AuditLog } from "../../../types/api"

type AuditTableProps = {
  logs: AuditLog[]
  isLoading: boolean
  error: string | null
  onSelectLog: (log: AuditLog) => void
  onResetFilters: () => void
}

function actionBadgeClass(action: AuditLog["action"]): string {
  if (action === "BLOCKED") {
    return "bg-brand-red/10 text-brand-red"
  }
  if (action === "ALLOWED") {
    return "bg-brand-green/10 text-brand-green"
  }
  return "bg-text-muted/10 text-text-muted"
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString()
}

function AuditTable({
  logs,
  isLoading,
  error,
  onSelectLog,
  onResetFilters,
}: AuditTableProps) {
  if (error) {
    return (
      <section className="bg-card-bg border border-border-color rounded-2xl p-6">
        <p className="text-brand-red">Unable to load audit ledger right now.</p>
      </section>
    )
  }

  return (
    <section className="bg-card-bg border border-border-color rounded-2xl overflow-hidden">
      <div className="p-6 border-b border-border-color">
        <h2 className="text-xl font-bold">Audit Ledger</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-white/5 text-text-muted text-xs uppercase tracking-wider">
            <tr>
              <th className="px-6 py-4 font-semibold">Timestamp</th>
              <th className="px-6 py-4 font-semibold">Action</th>
              <th className="px-6 py-4 font-semibold">Rule Triggered</th>
              <th className="px-6 py-4 font-semibold">Processing Time</th>
              <th className="px-6 py-4 font-semibold">Chain</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-color">
            {isLoading
              ? Array.from({ length: 10 }).map((_, index) => (
                  <tr key={`audit-skeleton-${index}`}>
                    <td className="px-6 py-5"><div className="h-4 w-40 bg-border-color/70 rounded animate-pulse" /></td>
                    <td className="px-6 py-5"><div className="h-5 w-20 bg-border-color/70 rounded animate-pulse" /></td>
                    <td className="px-6 py-5"><div className="h-4 w-32 bg-border-color/70 rounded animate-pulse" /></td>
                    <td className="px-6 py-5"><div className="h-4 w-16 bg-border-color/70 rounded animate-pulse" /></td>
                    <td className="px-6 py-5"><div className="h-4 w-8 bg-border-color/70 rounded animate-pulse" /></td>
                  </tr>
                ))
              : logs.length === 0
                ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12">
                      <div className="text-center">
                        <FileSearch className="w-10 h-10 text-text-muted mx-auto mb-3" />
                        <p className="text-lg font-semibold mb-2">No audit logs found</p>
                        <p className="text-text-muted mb-4">
                          Try adjusting filters or run a request through hooks.
                        </p>
                        <button
                          type="button"
                          onClick={onResetFilters}
                          className="px-4 py-2 rounded-lg border border-border-color text-text-muted hover:text-white hover:bg-white/5"
                        >
                          Clear filters
                        </button>
                      </div>
                    </td>
                  </tr>
                  )
              : logs.map((log) => (
                  <tr
                    key={log.id}
                    data-testid={`audit-row-${log.id}`}
                    className="hover:bg-white/5 transition-colors cursor-pointer"
                    onClick={() => onSelectLog(log)}
                  >
                    <td className="px-6 py-5 text-sm text-text-muted">{formatTimestamp(log.created_at)}</td>
                    <td className="px-6 py-5">
                      <span
                        className={`px-2.5 py-1 rounded text-[10px] font-bold uppercase ${actionBadgeClass(log.action)}`}
                      >
                        {log.action.toLowerCase()}
                      </span>
                    </td>
                    <td className="px-6 py-5 font-medium">{log.violation_type ?? "n/a"}</td>
                    <td className="px-6 py-5 text-sm text-text-muted">{log.processing_ms ?? 0}ms</td>
                    <td className="px-6 py-5">
                      {log.algorand_tx_id ? (
                        <a
                          href={`https://testnet.explorer.perawallet.app/tx/${log.algorand_tx_id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-text-muted hover:text-white"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      ) : (
                        <span className="text-text-muted">-</span>
                      )}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default AuditTable
