import React, { createContext, useContext, useState, useCallback } from 'react'
import { authApi } from '../api/client'

interface AuthUser { username: string; role: string }
interface AuthContextType {
  user: AuthUser | null; token: string | null; isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const s = localStorage.getItem('user')
    return s ? JSON.parse(s) : null
  })
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('access_token'))

  const login = useCallback(async (username: string, password: string) => {
    const res = await authApi.login(username, password)
    const { access_token, username: uname, role } = res.data
    localStorage.setItem('access_token', access_token)
    const u = { username: uname, role }
    localStorage.setItem('user', JSON.stringify(u))
    setToken(access_token)
    setUser(u)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, isAdmin: user?.role === 'admin', login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
