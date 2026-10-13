import type { RefObject } from "react"

import { useNativeModalDialog } from "../../../hooks/useNativeModalDialog"
import type { Policy } from "../../../types/api"

type DeleteConfirmationModalProps = {
  policy: Policy | null
  isDeleting: boolean
  fallbackFocusRef?: RefObject<HTMLElement | null>
  onCancel: () => void
  onConfirm: () => Promise<void>
}

function DeleteConfirmationModal({
  policy,
  isDeleting,
  fallbackFocusRef,
  onCancel,
  onConfirm,
}: DeleteConfirmationModalProps) {
  const { dialogRef, handleCancel, handleKeyDown } = useNativeModalDialog({
    isOpen: Boolean(policy),
    onClose: onCancel,
    fallbackFocusRef,
  })

  if (!policy) {
    return null
  }

  return (
    <dialog
      ref={dialogRef}
      data-testid="delete-confirmation-dialog"
      aria-labelledby="delete-policy-title"
      aria-describedby="delete-policy-description"
      aria-modal="true"
      onCancel={handleCancel}
      onKeyDown={handleKeyDown}
      className="fixed inset-0 m-0 flex h-full max-h-none w-full max-w-none items-center justify-center border-0 bg-transparent p-4 text-white backdrop:bg-black/50"
    >
      <div className="w-full max-w-md bg-card-bg border border-brand-red/40 rounded-2xl p-6">
        <h2 id="delete-policy-title" className="text-xl font-bold text-brand-red">Delete Policy</h2>
        <p id="delete-policy-description" className="text-sm text-text-muted mt-2">
          This action permanently deletes <span className="text-white">{policy.name}</span>.
        </p>

        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            data-dialog-initial-focus
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
    </dialog>
  )
}

export default DeleteConfirmationModal
