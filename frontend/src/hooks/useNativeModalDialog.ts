import {
  useEffect,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type RefObject,
  type SyntheticEvent,
} from "react"

type UseNativeModalDialogOptions = {
  isOpen: boolean
  onClose: () => void
  fallbackFocusRef?: RefObject<HTMLElement | null>
}

function useNativeModalDialog({
  isOpen,
  onClose,
  fallbackFocusRef,
}: UseNativeModalDialogOptions) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!isOpen) return

    const dialog = dialogRef.current
    if (!dialog) return

    const returnFocusTarget =
      document.activeElement instanceof HTMLElement ? document.activeElement : null

    if (!dialog.open) {
      if (typeof dialog.showModal === "function") {
        dialog.showModal()
      } else {
        // JSDOM has no modal-dialog implementation; keep the dialog testable there.
        dialog.setAttribute("open", "")
      }
    }
    dialog.querySelector<HTMLElement>("[data-dialog-initial-focus]")?.focus()

    return () => {
      if (dialog.open) {
        if (typeof dialog.close === "function") {
          dialog.close()
        } else {
          dialog.removeAttribute("open")
        }
      }

      const focusTarget = returnFocusTarget?.isConnected
        ? returnFocusTarget
        : fallbackFocusRef?.current
      if (focusTarget?.isConnected) focusTarget.focus()
    }
  }, [fallbackFocusRef, isOpen])

  function handleCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault()
    onCloseRef.current()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return

    const dialog = dialogRef.current
    if (!dialog) return

    const focusableElements = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], area[href], input:not([type="hidden"]), select, textarea, button, iframe, object, embed, [contenteditable="true"], [tabindex]:not([tabindex="-1"])',
      ),
    ).filter(
      (element) =>
        !element.hasAttribute("disabled") &&
        element.tabIndex >= 0 &&
        !element.closest("[hidden], [inert]"),
    )

    if (focusableElements.length === 0) {
      event.preventDefault()
      dialog.focus()
      return
    }

    const first = focusableElements[0]
    const last = focusableElements[focusableElements.length - 1]
    const activeElement = document.activeElement

    if (event.shiftKey && (activeElement === first || !dialog.contains(activeElement))) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && (activeElement === last || !dialog.contains(activeElement))) {
      event.preventDefault()
      first.focus()
    }
  }

  function handleBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === event.currentTarget) onCloseRef.current()
  }

  return { dialogRef, handleCancel, handleKeyDown, handleBackdropClick }
}

export { useNativeModalDialog }
