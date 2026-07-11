import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useAuth } from './AuthContext'

export type ThemeId = 'photon' | 'photon-web' | 'ocean' | 'forest' | 'graphite' | 'dark-hc'

type ThemeMeta = {
  id: ThemeId
  label: string
  description: string
}

type ThemeContextType = {
  theme: ThemeId
  themes: ThemeMeta[]
  setTheme: (next: ThemeId) => void
}

const THEME_STORAGE_PREFIX = 'ui_theme_pref'

const THEMES: ThemeMeta[] = [
  { id: 'photon', label: 'Photon Classic', description: 'Brand default orange + navy' },
  { id: 'photon-web', label: 'Photon Web Gold', description: 'Photon website inspired gold + black enterprise palette' },
  { id: 'ocean', label: 'Ocean Calm', description: 'Cool blue and cyan accents' },
  { id: 'forest', label: 'Forest Focus', description: 'Green-led enterprise contrast' },
  { id: 'graphite', label: 'Graphite Pro', description: 'Neutral steel and slate theme' },
  { id: 'dark-hc', label: 'High-Contrast Dark', description: 'Dark surfaces with strong contrast and vivid chart palette' },
]

const ThemeContext = createContext<ThemeContextType | null>(null)

function normalizeTheme(value: string | null): ThemeId {
  const valid = THEMES.map((t) => t.id)
  return valid.includes(String(value) as ThemeId) ? (value as ThemeId) : 'photon'
}

function storageKey(username?: string): string {
  return `${THEME_STORAGE_PREFIX}:${username || 'guest'}`
}

function applyThemeToDom(theme: ThemeId) {
  document.documentElement.setAttribute('data-theme', theme)
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [theme, setThemeState] = useState<ThemeId>(() => {
    const stored = localStorage.getItem(storageKey())
    return normalizeTheme(stored)
  })

  useEffect(() => {
    const key = storageKey(user?.username)
    const stored = localStorage.getItem(key)
    const next = normalizeTheme(stored)
    setThemeState(next)
    applyThemeToDom(next)
  }, [user?.username])

  useEffect(() => {
    applyThemeToDom(theme)
  }, [theme])

  const setTheme = useCallback((next: ThemeId) => {
    const normalized = normalizeTheme(next)
    setThemeState(normalized)
    localStorage.setItem(storageKey(user?.username), normalized)
    applyThemeToDom(normalized)
  }, [user?.username])

  const value = useMemo<ThemeContextType>(() => ({
    theme,
    themes: THEMES,
    setTheme,
  }), [theme, setTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
