import {
  Activity,
  CircleHelp,
  LayoutGrid,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  Settings,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react"
import { useCallback, useEffect, useId, useRef, useState, type FocusEvent, type MouseEvent } from "react"
import { FrameLogo } from "./FrameLogo"
import { Button } from "./Primitives"
import "./sidebar.css"

export type FoundationSidebarItem = {
  label: string
  href?: string
  target?: string
  icon: LucideIcon
  selected?: boolean
  disabled?: boolean
}

type FoundationSidebarProps = {
  primaryItems?: FoundationSidebarItem[]
  footerItems?: FoundationSidebarItem[]
  onCollapsedChange?: (collapsed: boolean) => void
  menuId?: string
  brandHref?: string
  brandLabel?: string
  sidebarLabel?: string
  primaryNavigationLabel?: string
  footerNavigationLabel?: string
}

const defaultPrimaryItems: FoundationSidebarItem[] = [
  { label: "Test", href: "#test-preview", icon: LayoutGrid, selected: true },
  { label: "Protection", href: "#protection-preview", icon: ShieldCheck },
  { label: "Activity", icon: Activity, disabled: true },
  { label: "Connect", icon: Plug, disabled: true },
]

const defaultFooterItems: FoundationSidebarItem[] = [
  { label: "Account settings", href: "#account-preview", icon: Settings },
  { label: "Help & feedback", href: "#preview-boundary", icon: CircleHelp },
]

export function FoundationSidebar({
  primaryItems = defaultPrimaryItems,
  footerItems = defaultFooterItems,
  onCollapsedChange,
  menuId = "preview-sidebar-menu",
  brandHref = "#test-preview",
  brandLabel = "SafeBot preview home",
  sidebarLabel = "Preview sidebar",
  primaryNavigationLabel = "Preview navigation",
  footerNavigationLabel = "More preview links",
}: FoundationSidebarProps = {}) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [navTooltip, setNavTooltip] = useState<{ label: string; top: number } | null>(null)
  const mobileMenuRef = useRef<HTMLDivElement>(null)
  const mobileToggleRef = useRef<HTMLButtonElement>(null)
  const tooltipId = useId()
  const showTimerRef = useRef<number | null>(null)
  const hideTimerRef = useRef<number | null>(null)

  const clearTooltipTimers = useCallback(() => {
    if (showTimerRef.current !== null) window.clearTimeout(showTimerRef.current)
    if (hideTimerRef.current !== null) window.clearTimeout(hideTimerRef.current)
    showTimerRef.current = null
    hideTimerRef.current = null
  }, [])

  const dismissTooltip = useCallback(() => {
    clearTooltipTimers()
    setNavTooltip(null)
  }, [clearTooltipTimers])

  const displayTooltip = useCallback((label: string, target: HTMLElement) => {
    if (!sidebarCollapsed || window.innerWidth <= 720) return
    clearTooltipTimers()
    const bounds = target.getBoundingClientRect()
    setNavTooltip({ label, top: bounds.top + bounds.height / 2 })
  }, [clearTooltipTimers, sidebarCollapsed])

  const queueTooltip = useCallback((label: string, target: HTMLElement) => {
    if (!sidebarCollapsed || window.innerWidth <= 720) return
    clearTooltipTimers()
    const bounds = target.getBoundingClientRect()
    const tooltip = { label, top: bounds.top + bounds.height / 2 }
    showTimerRef.current = window.setTimeout(() => {
      setNavTooltip(tooltip)
      showTimerRef.current = null
    }, 100)
  }, [clearTooltipTimers, sidebarCollapsed])

  const scheduleTooltipDismiss = useCallback((target: HTMLElement) => {
    if (document.activeElement === target) return
    if (showTimerRef.current !== null) window.clearTimeout(showTimerRef.current)
    showTimerRef.current = null
    if (hideTimerRef.current !== null) window.clearTimeout(hideTimerRef.current)
    hideTimerRef.current = window.setTimeout(() => {
      setNavTooltip(null)
      hideTimerRef.current = null
    }, 240)
  }, [])

  function handleCollapseToggle() {
    const nextCollapsed = !sidebarCollapsed
    setSidebarCollapsed(nextCollapsed)
    onCollapsedChange?.(nextCollapsed)
    dismissTooltip()
  }

  useEffect(() => {
    if (!mobileMenuOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      const activeElement = document.activeElement
      const focusIsInDisclosure = activeElement === mobileToggleRef.current
      const focusIsInMenu = Boolean(activeElement && mobileMenuRef.current?.contains(activeElement))
      if (event.key !== "Escape" || (!focusIsInDisclosure && !focusIsInMenu)) return
      event.preventDefault()
      setMobileMenuOpen(false)
      mobileToggleRef.current?.focus()
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [mobileMenuOpen])

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return
    const desktopQuery = window.matchMedia("(min-width: 721px)")
    const handleBreakpointChange = (event: MediaQueryListEvent) => {
      dismissTooltip()
      if (event.matches) setMobileMenuOpen(false)
    }
    desktopQuery.addEventListener("change", handleBreakpointChange)
    return () => desktopQuery.removeEventListener("change", handleBreakpointChange)
  }, [dismissTooltip])

  useEffect(() => () => clearTooltipTimers(), [clearTooltipTimers])

  useEffect(() => {
    if (!sidebarCollapsed) return
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return
      if (!navTooltip && showTimerRef.current === null && hideTimerRef.current === null) return
      event.preventDefault()
      dismissTooltip()
    }
    document.addEventListener("keydown", dismissOnEscape)
    return () => document.removeEventListener("keydown", dismissOnEscape)
  }, [dismissTooltip, navTooltip, sidebarCollapsed])

  function handleLocalNavigation(event: MouseEvent<HTMLAnchorElement>, href: string, target?: string) {
    const modifiedActivation = event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
    if (modifiedActivation || target === "_blank") return
    setMobileMenuOpen(false)
    if (window.innerWidth > 720) return

    let destination: URL
    try {
      destination = new URL(href, window.location.href)
    } catch {
      return
    }
    const current = new URL(window.location.href)
    const isSameDocumentHash = destination.origin === current.origin
      && destination.pathname === current.pathname
      && destination.search === current.search
      && Boolean(destination.hash)
    if (!isSameDocumentHash) return

    let targetId = destination.hash.slice(1)
    try {
      targetId = decodeURIComponent(targetId)
    } catch {
      targetId = destination.hash.slice(1)
    }
    const destinationElement = document.getElementById(targetId)
    if (!destinationElement) {
      window.setTimeout(() => mobileToggleRef.current?.focus(), 0)
      return
    }

    event.preventDefault()
    window.location.assign(destination.hash)
    const focusTarget = () => {
      destinationElement.scrollIntoView?.({ block: "start" })
      const isNativelyFocusable = destinationElement.matches(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]',
      )
      if (!isNativelyFocusable) {
        destinationElement.setAttribute("tabindex", "-1")
        destinationElement.addEventListener("blur", () => destinationElement.removeAttribute("tabindex"), { once: true })
      }
      destinationElement.focus({ preventScroll: true })
    }
    if (window.requestAnimationFrame) window.requestAnimationFrame(focusTarget)
    else window.setTimeout(focusTarget, 0)
  }

  function renderItem(item: FoundationSidebarItem) {
    const Icon = item.icon
    const describedBy = sidebarCollapsed && navTooltip?.label === item.label ? tooltipId : undefined
    const commonProps = {
      "aria-describedby": describedBy,
      "aria-label": item.label,
      className: "fd-nav__link",
      "data-tooltip": item.label,
      onBlur: dismissTooltip,
      onFocus: (event: FocusEvent<HTMLElement>) => displayTooltip(item.label, event.currentTarget),
      onMouseEnter: (event: MouseEvent<HTMLElement>) => queueTooltip(item.label, event.currentTarget),
      onMouseLeave: (event: MouseEvent<HTMLElement>) => scheduleTooltipDismiss(event.currentTarget),
      title: sidebarCollapsed ? item.label : undefined,
    }

    if (item.disabled || !item.href) {
      return (
        <span
          {...commonProps}
          aria-disabled="true"
          className="fd-nav__item"
          key={item.label}
          role="link"
        >
          <Icon aria-hidden="true" className="fd-nav__icon" size={20} />
          <span className="fd-nav__label">{item.label}</span>
        </span>
      )
    }

    const href = item.href
    return (
      <a
        {...commonProps}
        aria-current={item.selected ? "page" : undefined}
        className="fd-nav__link"
        href={href}
        key={item.label}
        onClick={(event) => handleLocalNavigation(event, href, item.target)}
        target={item.target}
      >
        <Icon aria-hidden="true" className="fd-nav__icon" size={20} />
        <span className="fd-nav__label">{item.label}</span>
      </a>
    )
  }

  return (
    <>
      <aside
        aria-label={sidebarLabel}
        className={"fd-sidebar" + (sidebarCollapsed ? " fd-sidebar--collapsed" : "") + (mobileMenuOpen ? " fd-sidebar--mobile-open" : "")}
        id="preview-sidebar"
      >
        <div className="fd-sidebar__header">
          <a className="fd-brand" href={brandHref} aria-label={brandLabel} onClick={(event) => handleLocalNavigation(event, brandHref)}>
            <FrameLogo size={28} showWordmark />
          </a>
          <Button
            aria-controls={menuId}
            aria-expanded={!sidebarCollapsed}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="fd-sidebar__collapse"
            onClick={handleCollapseToggle}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            variant="secondary"
          >
            {sidebarCollapsed ? <PanelLeftOpen aria-hidden="true" size={18} /> : <PanelLeftClose aria-hidden="true" size={18} />}
          </Button>
          <Button
            aria-controls={menuId}
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? "Close preview navigation" : "Open preview navigation"}
            className="fd-mobile-toggle"
            onClick={() => setMobileMenuOpen((open) => !open)}
            ref={mobileToggleRef}
            variant="secondary"
          >
            {mobileMenuOpen ? <X aria-hidden="true" size={18} /> : <Menu aria-hidden="true" size={18} />}
          </Button>
        </div>
        <div className="fd-sidebar__menu" id={menuId} ref={mobileMenuRef}>
          <nav aria-label={primaryNavigationLabel} className="fd-nav">
            {primaryItems.map(renderItem)}
          </nav>
          <nav aria-label={footerNavigationLabel} className="fd-sidebar__bottom">
            {footerItems.map(renderItem)}
          </nav>
        </div>
        {navTooltip && sidebarCollapsed && (
          <div
            className="fd-nav-tooltip"
            id={tooltipId}
            onMouseEnter={clearTooltipTimers}
            onMouseLeave={(event) => scheduleTooltipDismiss(event.currentTarget)}
            role="tooltip"
            style={{ top: navTooltip.top }}
          >
            {navTooltip.label}
          </div>
        )}
      </aside>
    </>
  )
}
