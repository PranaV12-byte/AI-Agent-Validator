import { useEffect, useState } from "react"

import ActivityTable from "../../components/shared/ActivityTable"
import KpiGrid from "../../components/shared/KpiGrid"
import PageHeader from "../../components/shared/PageHeader"
import UsageTrendChart from "../../components/shared/UsageTrendChart"
import { fetchAuditLogs } from "../../services/auditService"
import { fetchDashboardStats } from "../../services/dashboardService"
import type { AuditLog, DashboardStats } from "../../types/api"

function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [logs, setLogs] = useState<AuditLog[]>([])

  const [isStatsLoading, setIsStatsLoading] = useState(true)
  const [isLogsLoading, setIsLogsLoading] = useState(true)

  const [statsError, setStatsError] = useState<string | null>(null)
  const [logsError, setLogsError] = useState<string | null>(null)

  const [showEmptyState, setShowEmptyState] = useState(false)

  useEffect(() => {
    let mounted = true

    async function load() {
      setIsStatsLoading(true)
      setIsLogsLoading(true)
      setStatsError(null)
      setLogsError(null)

      try {
        const dashboard = await fetchDashboardStats()
        if (mounted) {
          setStats({
            total_requests: dashboard.total_requests,
            blocked_requests: dashboard.blocked_requests,
            avg_latency_ms: dashboard.avg_latency_ms,
          })
          setShowEmptyState(dashboard.total_requests === 0)
        }
      } catch {
        if (mounted) {
          setStatsError("Unable to fetch security metrics at this time.")
        }
      } finally {
        if (mounted) {
          setIsStatsLoading(false)
        }
      }

      try {
        const audit = await fetchAuditLogs({ page: 1, page_size: 20 })
        if (mounted) {
          setLogs(audit.logs)
        }
      } catch {
        if (mounted) {
          setLogsError("Unable to load recent activity right now.")
        }
      } finally {
        if (mounted) {
          setIsLogsLoading(false)
        }
      }
    }

    void load()

    return () => {
      mounted = false
    }
  }, [])

  return (
    <>
      <PageHeader />
      <KpiGrid stats={stats} isLoading={isStatsLoading} error={statsError} />
      <UsageTrendChart />
      {showEmptyState && !isStatsLoading ? (
        <section className="bg-card-bg border border-border-color rounded-2xl p-10 text-center mb-8">
          <h2 className="text-2xl font-semibold mb-2">No data found</h2>
          <p className="text-text-muted">Make your first API call to see data.</p>
        </section>
      ) : null}
      <ActivityTable logs={logs} isLoading={isLogsLoading} error={logsError} />
    </>
  )
}

export default DashboardPage
