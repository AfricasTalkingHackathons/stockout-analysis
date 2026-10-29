import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore } from './api'
import type { Meta, User } from './types'

interface AuthCtx {
  user: User | null
  meta: Meta | null
  ready: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => Promise<void>
  can: (permission: string) => boolean
  refreshMeta: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [ready, setReady] = useState(false)

  const refreshMeta = useCallback(() => {
    api.get<Meta>('/api/public/meta').then(setMeta).catch(() => setMeta(null))
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      tokenStore.clear()
      setUser(null)
    })
    refreshMeta()
    if (!tokenStore.get()) {
      setReady(true)
      return
    }
    api
      .get<User>('/api/auth/me')
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setReady(true))
  }, [refreshMeta])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/api/auth/login', { email, password })
    tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/api/auth/logout')
    } catch {
      /* token may already be invalid */
    }
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo<AuthCtx>(
    () => ({
      user,
      meta,
      ready,
      login,
      logout,
      refreshMeta,
      can: (p: string) => !!user?.permissions.includes(p),
    }),
    [user, meta, ready, login, logout, refreshMeta],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used inside AuthProvider')
  return c
}
