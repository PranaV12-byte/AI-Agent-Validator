import {
  FileText,
  LayoutGrid,
  Plug,
  Settings,
  ShieldCheck,
} from "lucide-react"
import type { ComponentType } from "react"
import { NavLink } from "react-router-dom"

import { useAuth } from "../../hooks/useAuth"

type NavItem = {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
}

const navItems: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutGrid },
  { to: "/audit-log", label: "Activity History", icon: FileText },
  { to: "/policies", label: "Protection Rules", icon: ShieldCheck },
  { to: "/integration", label: "Connect Your AI", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings },
]

function Sidebar() {
  const { user } = useAuth()

  return (
    <aside
      className="w-64 bg-sidebar-bg border-r border-border-color flex flex-col p-6 shrink-0"
      data-purpose="sidebar-navigation"
    >
      <div className="flex items-center gap-3 mb-12">
        <div className="w-10 h-10 bg-brand-green/20 rounded-lg flex items-center justify-center border border-brand-green/30">
          <ShieldCheck className="w-6 h-6 text-brand-green" />
        </div>
        <span className="text-xl font-bold tracking-tight">Safebot</span>
      </div>

      <nav className="flex-1 space-y-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                "flex items-center gap-3 px-4 py-3 rounded-xl font-medium transition-all",
                isActive
                  ? "bg-brand-green/10 text-brand-green"
                  : "text-text-muted hover:text-white hover:bg-white/5",
              ].join(" ")
            }
          >
            <item.icon className="w-5 h-5" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto flex items-center gap-3 p-2 bg-white/5 rounded-xl">
        <div className="w-10 h-10 rounded-full bg-border-color shrink-0" />
        <div className="overflow-hidden">
          <p className="text-sm font-medium truncate">{user?.company_name ?? "Tenant"}</p>
          <p className="text-xs text-text-muted truncate">{user?.email ?? "--"}</p>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
