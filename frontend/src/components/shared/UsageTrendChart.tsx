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
      <div className="relative w-full h-48 mt-4 overflow-hidden" data-purpose="mock-graph">
        <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 800 120">
          <path
            d="M0,100 Q100,90 200,85 T400,75 T600,60 T800,55"
            fill="none"
            stroke="#4ADE80"
            strokeWidth="2.5"
          />
          <path
            d="M0,115 Q100,110 200,112 T400,105 T600,108 T800,105"
            fill="none"
            stroke="#EF4444"
            strokeDasharray="4,2"
            strokeWidth="1.5"
          />
        </svg>
      </div>
    </section>
  )
}

export default UsageTrendChart
