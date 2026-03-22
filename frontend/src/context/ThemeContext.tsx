import type { ReactNode } from "react"
import { createContext, useContext } from "react"

type ThemeContextValue = {
  theme: "dark"
}

const ThemeContext = createContext<ThemeContextValue>({ theme: "dark" })

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <ThemeContext.Provider value={{ theme: "dark" }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
