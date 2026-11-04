// Light/dark theme: persisted, respects the OS preference on first visit,
// exposes chart-friendly colors to Recharts consumers.

import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

type Theme = 'light' | 'dark'

interface ThemeState {
  isDark: boolean
  toggle: () => void
  /** Colors for chart surfaces that must follow the theme. */
  chart: { grid: string; tick: string; tooltipBg: string }
}

const ThemeContext = createContext<ThemeState>({
  isDark: false,
  toggle: () => undefined,
  chart: { grid: '#e2e8f0', tick: '#64748b', tooltipBg: '#ffffff' },
})

function initial(): Theme {
  const stored = localStorage.getItem('evacuatesim-theme')
  if (stored === 'dark' || stored === 'light') return stored
  return 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('evacuatesim-theme', theme)
  }, [theme])

  const isDark = theme === 'dark'
  const value: ThemeState = {
    isDark,
    toggle: () => setTheme((t) => (t === 'light' ? 'dark' : 'light')),
    chart: isDark
      ? { grid: '#243044', tick: '#94a3b8', tooltipBg: '#1e293b' }
      : { grid: '#e2e8f0', tick: '#64748b', tooltipBg: '#ffffff' },
  }
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeState {
  return useContext(ThemeContext)
}
