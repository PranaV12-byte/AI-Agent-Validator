import { useEffect, useState } from "react"
import { toast } from "sonner"

import type { AuditLog } from "../../types/api"
import { exportAuditLogs, fetchAuditLogs } from "../../services/auditService"
import AuditDetailDrawer from "./components/AuditDetailDrawer"
import AuditFilterBar, { type ActionFilter } from "./components/AuditFilterBar"
import AuditTable from "./components/AuditTable"
import PaginationControls from "./components/PaginationControls"

const PAGE_SIZE = 10

function AuditLogPage() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [action, setAction] = useState<ActionFilter>("ALL")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [search, setSearch] = useState("")
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await fetchAuditLogs({
          page,
          page_size: PAGE_SIZE,
          action: action === "ALL" ? undefined : action,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
          search: search || undefined,
        })
        if (!cancelled) {
          setLogs(response.logs)
          setTotal(response.total)
        }
      } catch {
        if (!cancelled) {
          setError("Failed to fetch audit logs")
          toast.error("Failed to fetch audit logs")
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
  }, [action, page, startDate, endDate, search])

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Activity History</h1>
          <p className="text-text-muted">A record of every message your AI assistant checked.</p>
        </div>
        <button
          type="button"
          onClick={() => void exportAuditLogs({ action: action === "ALL" ? undefined : action, start_date: startDate || undefined, end_date: endDate || undefined, search: search || undefined })}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-card-bg border border-border-color rounded-lg hover:border-brand-green transition-colors"
        >
          Export CSV
        </button>
      </div>

      <AuditFilterBar
        action={action}
        startDate={startDate}
        endDate={endDate}
        search={search}
        onActionChange={(value) => {
          setAction(value)
          setPage(1)
        }}
        onStartDateChange={(value) => { setStartDate(value); setPage(1) }}
        onEndDateChange={(value) => { setEndDate(value); setPage(1) }}
        onSearchChange={(value) => { setSearch(value); setPage(1) }}
      />

      <AuditTable
        logs={logs}
        isLoading={isLoading}
        error={error}
        onSelectLog={setSelectedLog}
        onResetFilters={() => {
          setAction("ALL")
          setStartDate("")
          setEndDate("")
          setSearch("")
          setPage(1)
        }}
      />

      <PaginationControls
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPrevious={() => setPage((current) => Math.max(1, current - 1))}
        onNext={() => setPage((current) => current + 1)}
      />

      <AuditDetailDrawer log={selectedLog} onClose={() => setSelectedLog(null)} />
    </div>
  )
}

export default AuditLogPage
