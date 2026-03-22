import type { Policy } from "../../../types/api"

type DeleteConfirmationModalProps = {
  policy: Policy | null
  isDeleting: boolean
  onCancel: () => void
  onConfirm: () => Promise<void>
}

function DeleteConfirmationModal({
  policy,
  isDeleting,
  onCancel,
  onConfirm,
}: DeleteConfirmationModalProps) {
  if (!policy) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card-bg border border-brand-red/40 rounded-2xl p-6">
        <h2 className="text-xl font-bold text-brand-red">Delete Policy</h2>
        <p className="text-sm text-text-muted mt-2">
          This action permanently deletes <span className="text-white">{policy.name}</span>.
        </p>

        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-lg border border-border-color text-text-muted hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void onConfirm()}
            disabled={isDeleting}
            className="px-4 py-2 rounded-lg bg-brand-red/10 border border-brand-red/40 text-brand-red hover:bg-brand-red/20 disabled:opacity-50"
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </div>
    </div>
  )
}

export default DeleteConfirmationModal
