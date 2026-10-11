import {
  forwardRef,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react"

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "subtle"
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", className = "", type = "button", ...props },
  ref,
) {
  return <button className={"fd-button fd-button--" + variant + (className ? " " + className : "")} ref={ref} type={type} {...props} />
})

export function Card({ children, padded = false, className = "" }: { children: ReactNode; padded?: boolean; className?: string }) {
  return <section className={"fd-card" + (padded ? " fd-card--padded" : "") + (className ? " " + className : "")}>{children}</section>
}

export function StatusBadge({ children, variant = "neutral" }: { children: ReactNode; variant?: "preview" | "info" | "success" | "warning" | "danger" | "neutral" }) {
  return <span className={"fd-status fd-status--" + variant}>{children}</span>
}

type FieldProps = {
  label: string
  description?: string
  error?: string
  labelClassName?: string
}

type TextInputProps = FieldProps & Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "type"> & { type?: InputHTMLAttributes<HTMLInputElement>["type"] }

export function TextInput({ label, description, error, labelClassName = "", type = "text", className = "", ...props }: TextInputProps) {
  const id = useId()
  const descriptionId = id + "-description"
  const errorId = id + "-error"
  const describedBy = [description ? descriptionId : "", error ? errorId : "", props["aria-describedby"] ?? ""].filter(Boolean).join(" ") || undefined
  return (
    <div className="fd-field">
      <label className={"fd-field__label" + (labelClassName ? " " + labelClassName : "")} htmlFor={id}>{label}</label>
      <input
        {...props}
        aria-describedby={describedBy}
        aria-invalid={error ? true : props["aria-invalid"]}
        className={"fd-input" + (className ? " " + className : "")}
        id={id}
        type={type}
      />
      {description && <span className="fd-field__description" id={descriptionId}>{description}</span>}
      {error && <span className="fd-field__error" id={errorId}>{error}</span>}
    </div>
  )
}

type TextAreaProps = FieldProps & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id">

export function TextArea({ label, description, error, labelClassName = "", className = "", ...props }: TextAreaProps) {
  const id = useId()
  const descriptionId = id + "-description"
  const errorId = id + "-error"
  const describedBy = [description ? descriptionId : "", error ? errorId : "", props["aria-describedby"] ?? ""].filter(Boolean).join(" ") || undefined
  return (
    <div className="fd-field">
      <label className={"fd-field__label" + (labelClassName ? " " + labelClassName : "")} htmlFor={id}>{label}</label>
      <textarea
        {...props}
        aria-describedby={describedBy}
        aria-invalid={error ? true : props["aria-invalid"]}
        className={"fd-input fd-input--multiline" + (className ? " " + className : "")}
        id={id}
      />
      {description && <span className="fd-field__description" id={descriptionId}>{description}</span>}
      {error && <span className="fd-field__error" id={errorId}>{error}</span>}
    </div>
  )
}

type ModalProps = {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
}

export function Modal({ open, onClose, title, description, children, footer }: ModalProps) {
  const dialogId = useId()
  const titleId = dialogId + "-title"
  const descriptionId = dialogId + "-description"
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeRef.current?.focus()
    const backgroundElements = Array.from(document.querySelectorAll<HTMLElement>('[data-modal-background="true"]'))
    const backgroundState = backgroundElements.map((element) => ({
      element,
      inert: element.inert,
      inertAttribute: element.getAttribute("inert"),
      ariaHidden: element.getAttribute("aria-hidden"),
    }))
    const previousOverflow = document.body.style.overflow
    backgroundState.forEach(({ element }) => {
      element.inert = true
      element.setAttribute("inert", "")
      element.setAttribute("aria-hidden", "true")
    })
    document.body.style.overflow = "hidden"
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== "Tab" || !dialogRef.current) return
      const elements = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      ))
      if (elements.length === 0) {
        event.preventDefault()
        dialogRef.current.focus()
      } else if (event.shiftKey && document.activeElement === elements[0]) {
        event.preventDefault()
        elements[elements.length - 1].focus()
      } else if (!event.shiftKey && document.activeElement === elements[elements.length - 1]) {
        event.preventDefault()
        elements[0].focus()
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      backgroundState.forEach(({ element, inert, inertAttribute, ariaHidden }) => {
        element.inert = inert
        if (inertAttribute !== null) element.setAttribute("inert", inertAttribute)
        else element.removeAttribute("inert")
        if (ariaHidden === null) element.removeAttribute("aria-hidden")
        else element.setAttribute("aria-hidden", ariaHidden)
      })
      document.body.style.overflow = previousOverflow
      returnFocusRef.current?.focus()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fd-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div
        aria-describedby={description ? descriptionId : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className="fd-modal"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="fd-modal__header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p id={descriptionId}>{description}</p>}
          </div>
          <button aria-label="Close dialog" className="fd-modal__close" onClick={onClose} ref={closeRef} type="button">×</button>
        </header>
        <div className="fd-modal__body">{children}</div>
        {footer && <footer className="fd-modal__footer">{footer}</footer>}
      </div>
    </div>
  )
}

export type TabOption = { id: string; label: string; content: ReactNode }

export function Tabs({ label, tabs, defaultTab }: { label: string; tabs: TabOption[]; defaultTab: string }) {
  const [activeTab, setActiveTab] = useState(defaultTab)
  const baseId = useId()
  const selectedIndex = Math.max(0, tabs.findIndex((tab) => tab.id === activeTab))

  function onTabKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex = index
    if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length
    else if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length
    else if (event.key === "Home") nextIndex = 0
    else if (event.key === "End") nextIndex = tabs.length - 1
    else return
    event.preventDefault()
    setActiveTab(tabs[nextIndex].id)
    document.getElementById(baseId + "-tab-" + tabs[nextIndex].id)?.focus()
  }

  const active = tabs[selectedIndex]
  if (!active) return null
  return (
    <div className="fd-tabs">
      <div aria-label={label} className="fd-tabs__list" role="tablist">
        {tabs.map((tab, index) => (
          <button
            aria-controls={baseId + "-panel"}
            aria-selected={tab.id === active.id}
            className="fd-tabs__tab"
            id={baseId + "-tab-" + tab.id}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => onTabKeyDown(event, index)}
            role="tab"
            tabIndex={tab.id === active.id ? 0 : -1}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div aria-labelledby={baseId + "-tab-" + active.id} className="fd-tabs__panel" id={baseId + "-panel"} role="tabpanel">
        {active.content}
      </div>
    </div>
  )
}
