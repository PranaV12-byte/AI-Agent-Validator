import { Bell, Search } from "lucide-react"

function PageHeader() {
  return (
    <div className="flex justify-between items-start mb-10">
      <div>
        <h1 className="text-3xl font-bold mb-1">Security Overview</h1>
        <p className="text-text-muted">Real-time threat detection</p>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative">
          <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-text-muted" />
          </div>
          <input
            className="bg-card-bg border border-border-color rounded-lg pl-10 pr-4 py-2 text-sm focus:ring-1 focus:ring-brand-green focus:outline-none w-64"
            placeholder="Search..."
            type="text"
          />
        </div>
        <button
          className="relative p-2 bg-card-bg border border-border-color rounded-lg text-text-muted hover:text-white transition-colors"
          type="button"
          aria-label="Notifications"
        >
          <Bell className="h-6 w-6" />
          <span className="absolute top-2 right-2.5 block h-2 w-2 rounded-full bg-brand-red ring-2 ring-dashboard-bg" />
        </button>
      </div>
    </div>
  )
}

export default PageHeader
