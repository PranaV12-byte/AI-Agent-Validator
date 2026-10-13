import { Menu, X } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"

import Sidebar from "./Sidebar"

function Layout() {
  const location = useLocation()
  const menuButton = useRef<HTMLButtonElement>(null)
  const drawer = useRef<HTMLDialogElement>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  const closeMenu = useCallback(() => {
    if (drawer.current?.open) {
      drawer.current.close()
      menuButton.current?.focus()
    }
    setMenuOpen(false)
  }, [])

  useEffect(() => {
    closeMenu()
  }, [closeMenu, location.pathname])

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const desktop = window.matchMedia("(min-width: 768px)")
    const onChange = () => { if (desktop.matches) closeMenu() }
    desktop.addEventListener("change", onChange)
    return () => desktop.removeEventListener("change", onChange)
  }, [closeMenu])

  return (
    <div className="flex h-full bg-dashboard-bg text-white font-sans antialiased overflow-hidden">
      <div className="hidden md:flex shrink-0">
        <Sidebar />
      </div>
      <div className="flex min-w-0 min-h-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-border-color bg-sidebar-bg px-4 py-3 md:hidden">
          <button
            ref={menuButton}
            type="button"
            aria-label="Open navigation"
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation"
            onClick={() => {
              if (!drawer.current?.open) drawer.current?.showModal()
              setMenuOpen(true)
            }}
            className="rounded-lg border border-border-color p-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-green"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
          <span className="font-semibold">Safebot</span>
        </header>
        <main
          className="flex-1 min-w-0 min-h-0 bg-dashboard-bg p-4 md:p-8 overflow-y-auto"
          data-purpose="main-dashboard-view"
        >
          <Outlet />
        </main>
      </div>
      <dialog
        ref={drawer}
        id="mobile-navigation"
        aria-labelledby="mobile-navigation-title"
        onClose={() => setMenuOpen(false)}
        onCancel={(event) => { event.preventDefault(); closeMenu() }}
        onClick={(event) => { if (event.target === event.currentTarget) closeMenu() }}
        className="fixed inset-0 m-0 h-full max-h-none w-72 max-w-[calc(100%_-_2rem)] border-r border-border-color bg-sidebar-bg p-0 text-white backdrop:bg-black/60 md:hidden"
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="flex shrink-0 items-center justify-between border-b border-border-color px-6 py-3">
            <h2 id="mobile-navigation-title" className="font-semibold">Navigation</h2>
            <button
              type="button"
              aria-label="Close navigation"
              onClick={closeMenu}
              autoFocus
              className="rounded-lg p-2 text-text-muted hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-green"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Sidebar mobile onNavigate={closeMenu} />
          </div>
        </div>
      </dialog>
    </div>
  )
}

export default Layout
