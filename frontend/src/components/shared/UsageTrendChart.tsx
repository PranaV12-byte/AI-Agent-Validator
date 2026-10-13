export type UsageTrendPoint = {
  date: string
  allowed_requests: number
  redacted_requests: number
  blocked_requests: number
  error_requests: number
}

export type UsageTrendChartProps = {
  points: UsageTrendPoint[]
  isLoading: boolean
  error: string | null
}

type TrendMetric = Exclude<keyof UsageTrendPoint, "date">

const SERIES: { key: TrendMetric; label: string; color: string; marker: string }[] = [
  {
    key: "allowed_requests",
    label: "Allowed",
    color: "bg-brand-green",
    marker: "bg-brand-green",
  },
  {
    key: "redacted_requests",
    label: "Redacted",
    color: "bg-text-muted",
    marker: "bg-text-muted",
  },
  {
    key: "blocked_requests",
    label: "Blocked",
    color: "bg-brand-red",
    marker: "bg-brand-red",
  },
  {
    key: "error_requests",
    label: "Incomplete / errors",
    color: "bg-brand-red/50",
    marker: "bg-brand-red/50 border border-brand-red",
  },
]

function countFor(point: UsageTrendPoint, key: TrendMetric): number {
  const value = point[key]
  return Number.isFinite(value) ? Math.max(0, value) : 0
}

function totalFor(point: UsageTrendPoint): number {
  return SERIES.reduce((total, series) => total + countFor(point, series.key), 0)
}

function formatUtcDay(value: string): string {
  const date = new Date(`${value}T00:00:00.000Z`)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date)
}

function UsageTrendChart({ points, isLoading, error }: UsageTrendChartProps) {
  const maxTotal = Math.max(1, ...points.map(totalFor))
  const hasActivity = points.some((point) => totalFor(point) > 0)

  return (
    <section
      className="bg-card-bg border border-border-color rounded-2xl p-6 sm:p-8 mb-8"
      data-purpose="chart-container"
      aria-labelledby="usage-trend-title"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h2 id="usage-trend-title" className="text-xl font-bold">Usage Trend</h2>
        <ul aria-label="Request outcomes" className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {SERIES.map((series) => (
            <li key={series.key} className="flex items-center gap-2">
              <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${series.marker}`} />
              <span className="text-text-muted">{series.label}</span>
            </li>
          ))}
        </ul>
      </div>

      {isLoading ? (
        <p role="status" className="py-12 text-center text-sm text-text-muted">
          Loading usage trend…
        </p>
      ) : error ? (
        <p role="alert" className="py-12 text-center text-sm text-brand-red">
          Unable to load usage trend right now. Please try again later.
        </p>
      ) : points.length === 0 ? (
        <p role="status" className="py-12 text-center text-sm text-text-muted">
          No usage data is available for the last seven UTC days.
        </p>
      ) : (
        <figure className="mt-6">
          <figcaption className="mb-4 text-xs text-text-muted">
            Daily requests by UTC day · last seven days
          </figcaption>
          {!hasActivity ? (
            <p role="status" className="mb-4 text-sm text-text-muted">
              No requests recorded during this period.
            </p>
          ) : null}

          <div
            aria-hidden="true"
            className="grid grid-cols-7 gap-2 sm:gap-4 items-end border-b border-border-color pb-2"
          >
            {points.map((point) => (
              <div key={point.date} className="min-w-0 text-center">
                <div className="flex h-32 items-end justify-center">
                  <div className="flex h-full w-5 flex-col-reverse justify-start overflow-hidden rounded-t sm:w-8">
                    {SERIES.map((series) => {
                      const count = countFor(point, series.key)
                      const height = (count / maxTotal) * 100
                      return (
                        <div
                          key={series.key}
                          className={`w-full ${series.color}`}
                          style={{ height: `${height}%` }}
                        />
                      )
                    })}
                  </div>
                </div>
                <p className="mt-2 truncate text-[10px] text-text-muted sm:text-xs">
                  {formatUtcDay(point.date)}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-sm">
              <caption className="mb-2 text-left text-xs text-text-muted">
                Exact request counts for each UTC date
              </caption>
              <thead className="text-left text-xs text-text-muted">
                <tr>
                  <th scope="col" className="py-2 pr-4 font-medium">UTC date</th>
                  {SERIES.map((series) => (
                    <th key={series.key} scope="col" className="px-2 py-2 text-right font-medium">
                      {series.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color">
                {points.map((point) => (
                  <tr key={point.date}>
                    <th scope="row" className="py-2 pr-4 text-left font-medium whitespace-nowrap">
                      <time dateTime={point.date}>{point.date}</time>
                    </th>
                    {SERIES.map((series) => (
                      <td key={series.key} className="px-2 py-2 text-right tabular-nums">
                        {countFor(point, series.key).toLocaleString()}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-text-muted">
              Incomplete / errors includes requests with only a pre-check recorded;
              in-flight checks may later resolve as allowed or redacted.
            </p>
          </div>
        </figure>
      )}
    </section>
  )
}

export default UsageTrendChart
