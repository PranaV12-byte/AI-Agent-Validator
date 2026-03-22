import { Ban, CheckCircle2, ShieldCheck, Zap } from "lucide-react"
import type { ComponentType } from "react"

import type { DashboardStats } from "../../types/api"

type TrendTone = "green" | "red" | "muted"

type KpiItem = {
  label: string
  value: string
  trend: string
  trendTone: TrendTone
  iconTone: string
  Icon: ComponentType<{ className?: string }>
}

type KpiGridProps = {
  stats: DashboardStats | null
  isLoading: boolean
  error: string | null
}

const trendClass: Record<TrendTone, string> = {
  green: "text-brand-green",
  red: "text-brand-red",
  muted: "text-text-muted",
}

function buildKpis(stats: DashboardStats | null): KpiItem[] {
  const values = stats ?? {
    total_requests: 0,
    blocked_requests: 0,
    avg_latency_ms: 0,
  }

  const allowedRequests = Math.max(0, values.total_requests - values.blocked_requests)
  const blockRate = values.total_requests
    ? (values.blocked_requests / values.total_requests) * 100
    : 0

  return [
    {
      label: "Requests Today",
      value: values.total_requests.toLocaleString(),
      trend: `${blockRate.toFixed(1)}% block rate`,
      trendTone: "green",
      iconTone: "bg-brand-green/10 text-brand-green",
      Icon: ShieldCheck,
    },
    {
      label: "Blocked",
      value: values.blocked_requests.toLocaleString(),
      trend: "Threats blocked",
      trendTone: "red",
      iconTone: "bg-brand-red/10 text-brand-red",
      Icon: Ban,
    },
    {
      label: "Allowed",
      value: allowedRequests.toLocaleString(),
      trend: "Requests allowed",
      trendTone: "green",
      iconTone: "bg-brand-green/10 text-brand-green",
      Icon: CheckCircle2,
    },
    {
      label: "Avg Latency",
      value: `${Math.round(values.avg_latency_ms)}ms`,
      trend: "Last 7 days",
      trendTone: "muted",
      iconTone: "bg-sky-500/10 text-sky-500",
      Icon: Zap,
    },
  ]
}

function KpiGrid({ stats, isLoading, error }: KpiGridProps) {
  if (error) {
    return (
      <div className="bg-card-bg border border-border-color rounded-2xl p-6 mb-8">
        <p className="text-brand-red">Unable to fetch security metrics at this time.</p>
      </div>
    )
  }

  const kpis = buildKpis(stats)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      {kpis.map((kpi) => (
        <div
          key={kpi.label}
          className="bg-card-bg border border-border-color rounded-2xl p-6"
          data-purpose="kpi-card"
        >
          <div className="flex justify-between items-center mb-6">
            <div className={`p-2 rounded-lg ${kpi.iconTone}`}>
              <kpi.Icon className="h-6 w-6" />
            </div>
            <span className={`text-sm font-medium ${trendClass[kpi.trendTone]}`}>
              {isLoading ? "Loading..." : kpi.trend}
            </span>
          </div>
          <p className="text-text-muted text-sm mb-1">{kpi.label}</p>
          {isLoading ? (
            <div className="h-9 w-24 bg-border-color/70 rounded animate-pulse" />
          ) : (
            <p className="text-3xl font-bold">{kpi.value}</p>
          )}
        </div>
      ))}
    </div>
  )
}

export default KpiGrid
