import { Component, type ErrorInfo, type ReactNode } from "react"

type Props = { children: ReactNode }
type State = { hasError: boolean }

class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("ErrorBoundary caught:", error, info.componentStack)
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-full bg-dashboard-bg text-white flex items-center justify-center p-6">
          <div className="text-center space-y-4 max-w-sm">
            <p className="text-xl font-bold">Something went wrong</p>
            <p className="text-text-muted text-sm">
              An unexpected error occurred. Refresh the page to continue.
            </p>
            <button
              type="button"
              onClick={() => this.setState({ hasError: false })}
              className="px-4 py-2 bg-brand-green/10 border border-brand-green/30 text-brand-green rounded-lg text-sm hover:bg-brand-green/20 transition-colors"
            >
              Try again
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
