import { CheckCircle2, Circle } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import ActivityTable from "../../components/shared/ActivityTable"
import KpiGrid from "../../components/shared/KpiGrid"
import PageHeader from "../../components/shared/PageHeader"
import UsageTrendChart from "../../components/shared/UsageTrendChart"
import { fetchAuditLogs } from "../../services/auditService"
import { fetchDashboardStats } from "../../services/dashboardService"
import { fetchPolicies } from "../../services/policyService"
import type { AuditLog, DashboardStats } from "../../types/api"

type ChecklistStep = {
  label: string
  done: boolean
  action: (() => void) | null
  actionLabel?: string
  hint?: string
}

function OnboardingChecklist({ steps }: { steps: ChecklistStep[] }) {
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
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [policyCount, setPolicyCount] = useState<number | null>(null)

  const [isStatsLoading, setIsStatsLoading] = useState(true)
  const [isLogsLoading, setIsLogsLoading] = useState(true)

  const [statsError, setStatsError] = useState<string | null>(null)
  const [logsError, setLogsError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function load() {
      setIsStatsLoading(true)
      setIsLogsLoading(true)
      setStatsError(null)
      setLogsError(null)

      const [dashboardResult, auditResult, policiesResult] = await Promise.allSettled([
        fetchDashboardStats(),
        fetchAuditLogs({ page: 1, page_size: 20 }),
        fetchPolicies(),
      ])

      if (!mounted) return

      if (dashboardResult.status === "fulfilled") {
        setStats({
          total_requests: dashboardResult.value.total_requests,
          blocked_requests: dashboardResult.value.blocked_requests,
          allowed_requests: dashboardResult.value.allowed_requests,
          redacted_requests: dashboardResult.value.redacted_requests,
          error_requests: dashboardResult.value.error_requests,
          avg_latency_ms: dashboardResult.value.avg_latency_ms,
          daily_trend: dashboardResult.value.daily_trend,
        })
      } else {
        setStatsError("Unable to fetch security metrics at this time.")
      }
      setIsStatsLoading(false)

      if (auditResult.status === "fulfilled") {
        setLogs(auditResult.value.logs)
      } else {
        setLogsError("Unable to load recent activity right now.")
      }
      setIsLogsLoading(false)

      if (policiesResult.status === "fulfilled") {
        setPolicyCount(policiesResult.value.total)
      } else {
        setPolicyCount(0)
      }
    }

    void load()

    function onVisibilityChange() {
      if (document.visibilityState === "visible" && mounted) {
        void load()
      }
    }
    document.addEventListener("visibilitychange", onVisibilityChange)
    const interval = setInterval(() => { if (mounted) void load() }, 5 * 60 * 1000)

    return () => {
      mounted = false
      document.removeEventListener("visibilitychange", onVisibilityChange)
      clearInterval(interval)
    }
  }, [])

  const hasActivity = (stats?.total_requests ?? 0) > 0
  const hasPolicy = (policyCount ?? 0) > 0

  const checklistSteps: ChecklistStep[] = [
    { label: "Create your account", done: true, action: null },
    {
      label: "Add your first protection rule",
      done: hasPolicy,
      action: hasPolicy ? null : () => navigate("/policies"),
      actionLabel: "Go to Protection Rules",
    },
    {
      label: "Connect your AI tool",
      done: hasActivity,
      action: hasActivity ? null : () => navigate("/integration"),
      actionLabel: "View Setup Guide",
    },
    {
      label: "Send a test message",
      done: hasActivity,
      action: null,
      hint: hasActivity ? undefined : "Complete the steps above first",
    },
  ]

  const allDone = checklistSteps.every((s) => s.done)
  const showChecklist = !isStatsLoading && !allDone && policyCount !== null

  return (
    <>
      <PageHeader />
      <KpiGrid stats={stats} isLoading={isStatsLoading} error={statsError} />
      <UsageTrendChart
        points={stats?.daily_trend ?? []}
        isLoading={isStatsLoading}
        error={statsError}
      />
      {showChecklist ? <OnboardingChecklist steps={checklistSteps} /> : null}
      <ActivityTable logs={logs} isLoading={isLogsLoading} error={logsError} />
    </>
  )
}

export default DashboardPage
