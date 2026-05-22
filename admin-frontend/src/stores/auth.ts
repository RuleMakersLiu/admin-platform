import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  adminId: number
  username: string
  realName: string
  tenantId: number
  groupName?: string
  isSuper?: boolean
  permissions: string[]
}

interface AuthState {
  token: string | null
  user: User | null
  setToken: (token: string) => void
  setUser: (user: User) => void
  logout: () => void
  hasPermission: (permission: string) => boolean
  hasAnyPermission: (permissions: string[]) => boolean
}

const normalizePermission = (permission: string) => {
  const value = String(permission || '').trim()
  if (!value || value === '*') return value
  if (value.includes(':')) return value.toLowerCase()
  const parts = value.replace(/-/g, '_').split('_').filter(Boolean)
  return parts.length >= 3 ? parts.join(':').toLowerCase() : value.toLowerCase()
}

const expandPermissions = (permissions: string[] = []) => {
  const set = new Set<string>()
  permissions.forEach((item) => {
    const normalized = normalizePermission(item)
    if (!normalized) return
    set.add(normalized)
    set.add(normalized.replace(/:/g, '_'))
  })
  return Array.from(set)
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user: { ...user, permissions: expandPermissions(user.permissions) } }),
      logout: () => set({ token: null, user: null }),
      hasPermission: (permission) => {
        const { user } = get()
        if (!user) return false
        // 超级管理员拥有所有权限
        if (user.isSuper || user.permissions.includes('*')) return true
        const normalized = normalizePermission(permission)
        return user.permissions.includes(normalized) || user.permissions.includes(normalized.replace(/:/g, '_'))
      },
      hasAnyPermission: (permissions) => {
        if (!permissions.length) return true
        return permissions.some((permission) => get().hasPermission(permission))
      },
    }),
    {
      name: 'auth-storage',
    }
  )
)
