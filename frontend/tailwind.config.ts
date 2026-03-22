import type { Config } from "tailwindcss"

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "dashboard-bg": "#0D1111",
        "sidebar-bg": "#090C0C",
        "card-bg": "#141A1A",
        "border-color": "#232A2A",
        "text-muted": "#8E9494",
        "brand-green": "#4ADE80",
        "brand-red": "#EF4444",
      },
    },
  },
  plugins: [],
} satisfies Config
