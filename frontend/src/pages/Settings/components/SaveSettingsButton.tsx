type SaveSettingsButtonProps = {
  disabled: boolean
  isSaving: boolean
  hasUnsavedChanges: boolean
  onClick: () => Promise<void>
}

function SaveSettingsButton({
  disabled,
  isSaving,
  hasUnsavedChanges,
  onClick,
}: SaveSettingsButtonProps) {
  return (
    <button
      type="button"
      data-testid="settings-save-button"
      disabled={disabled || isSaving}
      onClick={() => void onClick()}
      className="sticky bottom-4 ml-auto block rounded-lg bg-brand-green/10 border border-brand-green/30 text-brand-green px-5 py-3 font-medium hover:bg-brand-green/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {isSaving ? "Saving..." : hasUnsavedChanges ? "Save Unsaved Changes" : "Saved"}
    </button>
  )
}

export default SaveSettingsButton
