import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  adminId: number
  username: string
  realName: string
  tenantId: number
  permissions: string[]
}

interface AuthState {
  token: string | null
  user: User | null
  setToken: (token: string) => void
  setUser: (user: User) => void
  logout: () => void
  hasPermission: (permission: string) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      logout: () => set({ token: null, user: null }),
      hasPermission: (permission) => {
        const { user } = get()
        if (!user) return false
        // 超级管理员拥有所有权限
        if (user.permissions.includes('*')) return true
        return user.permissions.includes(permission)
      },
    }),
    {
      name: 'auth-storage',
    }
  )
)
