type ActionFilter = "ALL" | "BLOCKED" | "ALLOWED" | "REDACTED"

type AuditFilterBarProps = {
  action: ActionFilter
  startDate: string
  endDate: string
  onActionChange: (value: ActionFilter) => void
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
}

function AuditFilterBar({
  action,
  startDate,
  endDate,
  onActionChange,
  onStartDateChange,
  onEndDateChange,
}: AuditFilterBarProps) {
  return (
    <div className="bg-card-bg border border-border-color rounded-2xl p-5 flex flex-col lg:flex-row gap-4 lg:items-end lg:justify-between">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full">
        <div>
          <label htmlFor="action-filter" className="block text-sm text-text-muted mb-2">
            Action
          </label>
          <select
            id="action-filter"
            data-testid="action-filter"
            value={action}
            onChange={(event) => onActionChange(event.target.value as ActionFilter)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          >
            <option value="ALL">All</option>
            <option value="ALLOWED">Allowed</option>
            <option value="BLOCKED">Blocked</option>
            <option value="REDACTED">Redacted</option>
          </select>
        </div>

        <div>
          <label htmlFor="start-date" className="block text-sm text-text-muted mb-2">
            Start date
          </label>
          <input
            id="start-date"
            type="date"
            value={startDate}
            onChange={(event) => onStartDateChange(event.target.value)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>

        <div>
          <label htmlFor="end-date" className="block text-sm text-text-muted mb-2">
            End date
          </label>
          <input
            id="end-date"
            type="date"
            value={endDate}
            onChange={(event) => onEndDateChange(event.target.value)}
            className="w-full bg-dashboard-bg border border-border-color rounded-lg px-3 py-2.5 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none"
          />
        </div>
      </div>
    </div>
  )
}

export type { ActionFilter }
export default AuditFilterBar
