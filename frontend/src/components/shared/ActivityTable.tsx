import { Link as LinkIcon } from "lucide-react"

import type { AuditLog } from "../../types/api"
import { formatTimeAgo } from "../../utils/format"

type IncidentStatus = "BLOCKED" | "ALLOWED" | "REDACTED"

type Incident = {
  id: string
  time: string
  status: IncidentStatus
  incidentType: string
  details: string
  latency: string
}

type ActivityTableProps = {
  logs: AuditLog[]
  isLoading: boolean
  error: string | null
}

function statusClass(status: IncidentStatus): string {
  if (status === "BLOCKED") {
    return "bg-brand-red/10 text-brand-red"
  }

  if (status === "ALLOWED") {
    return "bg-brand-green/10 text-brand-green"
  }

  return "bg-text-muted/10 text-text-muted"
}

function toIncident(log: AuditLog): Incident {
  return {
    id: log.id,
    time: formatTimeAgo(log.created_at),
    status: log.action,
    incidentType: log.violation_type
      ? log.violation_type.replaceAll("_", " ")
      : "General Query",
    details: log.input_preview ?? "No details",
    latency: `${log.processing_ms ?? 0}ms`,
  }
}

function ActivityTable({ logs, isLoading, error }: ActivityTableProps) {
  if (error) {
    return (
      <section className="bg-card-bg border border-border-color rounded-2xl p-6">
        <p className="text-brand-red">Unable to load recent activity right now.</p>
      </section>
    )
  }

  const incidents = logs.map(toIncident)

  if (!isLoading && incidents.length === 0) {
    return (
      <section className="bg-card-bg border border-border-color rounded-2xl p-10 text-center">
        <p className="text-2xl mb-2">No data found</p>
        <p className="text-text-muted">Make your first API call to see data.</p>
      </section>
    )
  }

  return (
    <section
      className="bg-card-bg border border-border-color rounded-2xl overflow-hidden"
      data-purpose="table-container"
    >
      <div className="p-6 border-b border-border-color">
        <h2 className="text-xl font-bold">Recent Activity</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-white/5 text-text-muted text-xs uppercase tracking-wider">
            <tr>
              <th className="px-6 py-4 font-semibold">Time</th>
              <th className="px-6 py-4 font-semibold">Status</th>
              <th className="px-6 py-4 font-semibold">Incident Type</th>
              <th className="px-6 py-4 font-semibold">Details</th>
              <th className="px-6 py-4 font-semibold">Latency</th>
              <th className="px-6 py-4 font-semibold">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-color">
            {isLoading
              ? Array.from({ length: 4 }).map((_, index) => (
                  <tr key={`skeleton-${index}`} className="hover:bg-white/5 transition-colors">
                    <td className="px-6 py-5">
                      <div className="h-4 w-16 bg-border-color/70 rounded animate-pulse" />
                    </td>
                    <td className="px-6 py-5">
                      <div className="h-5 w-14 bg-border-color/70 rounded animate-pulse" />
                    </td>
                    <td className="px-6 py-5">
                      <div className="h-4 w-28 bg-border-color/70 rounded animate-pulse" />
                    </td>
                    <td className="px-6 py-5">
                      <div className="h-4 w-44 bg-border-color/70 rounded animate-pulse" />
                    </td>
                    <td className="px-6 py-5">
                      <div className="h-4 w-14 bg-border-color/70 rounded animate-pulse" />
                    </td>
                    <td className="px-6 py-5">
                      <div className="h-4 w-4 bg-border-color/70 rounded animate-pulse" />
                    </td>
                  </tr>
                ))
              : incidents.map((incident) => (
              <tr key={incident.id} className="hover:bg-white/5 transition-colors">
                <td className="px-6 py-5 text-sm text-text-muted">{incident.time}</td>
                <td className="px-6 py-5">
                  <span
                    className={`px-2.5 py-1 rounded text-[10px] font-bold uppercase ${statusClass(incident.status)}`}
                  >
                    {incident.status.toLowerCase()}
                  </span>
                </td>
                <td className="px-6 py-5 font-medium">{incident.incidentType}</td>
                <td className="px-6 py-5 text-xs font-mono text-text-muted max-w-xs truncate">
                  {incident.details}
                </td>
                <td className="px-6 py-5 text-sm text-text-muted">{incident.latency}</td>
                <td className="px-6 py-5">
                  <button
                    className="text-text-muted hover:text-white"
                    type="button"
                    aria-label={`Open incident ${incident.id}`}
                  >
                    <LinkIcon className="h-5 w-5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default ActivityTable
