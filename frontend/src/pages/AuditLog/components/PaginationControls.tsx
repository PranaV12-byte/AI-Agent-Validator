type PaginationControlsProps = {
  page: number
  pageSize: number
  total: number
  onPrevious: () => void
  onNext: () => void
}

function PaginationControls({
  page,
  pageSize,
  total,
  onPrevious,
  onNext,
}: PaginationControlsProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex items-center justify-between bg-card-bg border border-border-color rounded-2xl p-4">
      <p className="text-sm text-text-muted">
        Page {page} of {totalPages} ({total} records)
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onPrevious}
          disabled={page <= 1}
          className="px-3 py-2 rounded-lg border border-border-color text-text-muted hover:text-white hover:bg-white/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={page >= totalPages}
          className="px-3 py-2 rounded-lg border border-border-color text-text-muted hover:text-white hover:bg-white/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  )
}

export default PaginationControls
