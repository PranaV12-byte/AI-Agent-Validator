import { Outlet } from "react-router-dom"

import Sidebar from "./Sidebar"

function Layout() {
  return (
    <div className="flex h-full bg-dashboard-bg text-white font-sans antialiased overflow-hidden">
      <Sidebar />
      <main
        className="flex-1 bg-dashboard-bg p-8 overflow-y-auto"
        data-purpose="main-dashboard-view"
      >
        <Outlet />
      </main>
    </div>
  )
}

export default Layout
