function UsageTrendChart() {
  return (
    <section
      className="bg-card-bg border border-border-color rounded-2xl p-8 mb-8"
      data-purpose="chart-container"
    >
      <div className="flex justify-between items-center mb-8">
        <h2 className="text-xl font-bold">Usage Trend</h2>
        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-brand-green" />
            <span className="text-text-muted">Allowed</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-brand-red" />
            <span className="text-text-muted">Blocked</span>
          </div>
        </div>
      </div>
      <p className="text-text-muted text-sm text-center py-8" data-purpose="chart-placeholder">
        Activity chart coming soon. Your message history will appear here once your AI is connected.
      </p>
    </section>
  )
}

export default UsageTrendChart
