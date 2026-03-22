import { Link } from "react-router-dom"

function NotFound() {
  return (
    <div className="h-full bg-dashboard-bg text-white flex items-center justify-center px-6">
      <div className="bg-card-bg border border-border-color rounded-2xl p-10 text-center max-w-md w-full">
        <p className="text-brand-red text-sm font-semibold mb-2">404</p>
        <h1 className="text-3xl font-bold mb-3">Page Not Found</h1>
        <p className="text-text-muted mb-6">
          This route does not exist in the Safebot dashboard.
        </p>
        <Link
          to="/dashboard"
          className="inline-flex px-4 py-2 rounded-lg bg-brand-green/10 text-brand-green hover:bg-brand-green/20 transition-colors"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  )
}

export default NotFound
