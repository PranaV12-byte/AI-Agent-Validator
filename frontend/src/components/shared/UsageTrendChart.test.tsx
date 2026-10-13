import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import UsageTrendChart, {
  type UsageTrendChartProps,
  type UsageTrendPoint,
} from "./UsageTrendChart"

afterEach(cleanup)

const points: UsageTrendPoint[] = [
  {
    date: "2026-10-07",
    allowed_requests: 2,
    redacted_requests: 1,
    blocked_requests: 0,
    error_requests: 0,
  },
  {
    date: "2026-10-08",
    allowed_requests: 0,
    redacted_requests: 0,
    blocked_requests: 1,
    error_requests: 0,
  },
  {
    date: "2026-10-09",
    allowed_requests: 3,
    redacted_requests: 0,
    blocked_requests: 0,
    error_requests: 1,
  },
  {
    date: "2026-10-10",
    allowed_requests: 0,
    redacted_requests: 2,
    blocked_requests: 0,
    error_requests: 0,
  },
  {
    date: "2026-10-11",
    allowed_requests: 1,
    redacted_requests: 0,
    blocked_requests: 1,
    error_requests: 0,
  },
  {
    date: "2026-10-12",
    allowed_requests: 2,
    redacted_requests: 1,
    blocked_requests: 0,
    error_requests: 0,
  },
  {
    date: "2026-10-13",
    allowed_requests: 4,
    redacted_requests: 0,
    blocked_requests: 1,
    error_requests: 0,
  },
]

function renderChart(
  overrides: Partial<UsageTrendChartProps> = {},
) {
  return render(
    <UsageTrendChart
      points={points}
      isLoading={false}
      error={null}
      {...overrides}
    />,
  )
}

describe("UsageTrendChart", () => {
  it("shows the UTC trend and exact counts for each outcome", () => {
    renderChart()

    expect(screen.getByText("Daily requests by UTC day · last seven days")).toBeInTheDocument()
    expect(screen.getByRole("table", { name: "Exact request counts for each UTC date" })).toBeInTheDocument()
    expect(
      screen.getByText(/in-flight checks may later resolve as allowed or redacted/i),
    ).toBeInTheDocument()

    const firstDay = screen.getByRole("row", { name: /2026-10-07/ })
    expect(within(firstDay).getByText("2")).toBeInTheDocument()
    expect(within(firstDay).getByText("1")).toBeInTheDocument()
    expect(within(firstDay).getAllByText("0")).toHaveLength(2)

    const errorDay = screen.getByRole("row", { name: /2026-10-09/ })
    expect(within(errorDay).getByText("1")).toBeInTheDocument()
  })

  it("announces the loading state", () => {
    renderChart({ isLoading: true })
    expect(screen.getByRole("status")).toHaveTextContent("Loading usage trend")
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("shows a safe error state without exposing supplied error details", () => {
    renderChart({ error: "synthetic backend diagnostic" })
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load usage trend")
    expect(screen.queryByText("synthetic backend diagnostic")).not.toBeInTheDocument()
  })

  it("explains when no trend points are available", () => {
    renderChart({ points: [] })
    expect(screen.getByRole("status")).toHaveTextContent("No usage data is available")
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("shows zero counts for a returned zero-activity period", () => {
    const zeroPoints = points.map((point) => ({
      ...point,
      allowed_requests: 0,
      redacted_requests: 0,
      blocked_requests: 0,
      error_requests: 0,
    }))
    renderChart({ points: zeroPoints })

    expect(screen.getByRole("status")).toHaveTextContent("No requests recorded during this period")
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.getAllByText("0")).toHaveLength(28)
  })
})
