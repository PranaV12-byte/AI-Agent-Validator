import { CheckCircle2, Circle } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import ActivityTable from "../../components/shared/ActivityTable"
import KpiGrid from "../../components/shared/KpiGrid"
import PageHeader from "../../components/shared/PageHeader"
import UsageTrendChart from "../../components/shared/UsageTrendChart"
import { fetchAuditLogs } from "../../services/auditService"
import { fetchDashboardStats } from "../../services/dashboardService"
import type { AuditLog, DashboardStats } from "../../types/api"

function OnboardingChecklist() {
  const navigate = useNavigate()

  const steps = [
    {
      label: "Create your account",
      done: true,
      action: null,
    },
    {
      label: "Add your first protection rule",
      done: false,
      action: () => navigate("/policies"),
      actionLabel: "Go to Protection Rules",
    },
    {
      label: "Connect your AI tool",
      done: false,
      action: () => navigate("/integration"),
      actionLabel: "View Setup Guide",
    },
    {
      label: "Send a test message",
      done: false,
      action: null,
      hint: "Complete the steps above first",
    },
  ]

  return (
    <section className="bg-card-bg border border-border-color rounded-2xl p-8 mb-8">
      <h2 className="text-xl font-bold mb-1">Welcome to Safebot — let's get you set up</h2>
      <p className="text-text-muted text-sm mb-6">Follow these steps to protect your AI assistant.</p>
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={index} className="flex items-center gap-4">
            {step.done ? (
              <CheckCircle2 className="w-5 h-5 text-brand-green shrink-0" />
            ) : (
              <Circle className="w-5 h-5 text-text-muted shrink-0" />
            )}
            <span className={`text-sm flex-1 ${step.done ? "line-through text-text-muted" : ""}`}>
              {step.label}
            </span>
            {step.action ? (
              <button
                type="button"
                onClick={step.action}
                className="text-xs text-brand-green hover:underline"
              >
                {step.actionLabel}
              </button>
            ) : step.hint ? (
              <span className="text-xs text-text-muted">{step.hint}</span>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}

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

    // Refetch when the tab regains focus so data stays fresh.
    function onVisibilityChange() {
      if (document.visibilityState === "visible" && mounted) {
        void load()
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange)

    // Poll every 5 minutes as a background refresh.
    const interval = setInterval(() => { if (mounted) void load() }, 5 * 60 * 1000)

    return () => {
      mounted = false
      document.removeEventListener("visibilitychange", onVisibilityChange)
      clearInterval(interval)
    }
  }, [])

  return (
    <>
      <PageHeader />
      <KpiGrid stats={stats} isLoading={isStatsLoading} error={statsError} />
      <UsageTrendChart />
      {showEmptyState && !isStatsLoading ? <OnboardingChecklist /> : null}
      <ActivityTable logs={logs} isLoading={isLogsLoading} error={logsError} />
    </>
  )
}

export default DashboardPage
