import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
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

export const DEVELOPER_PORTAL_PERMISSIONS = ['portal:developer', 'developer:project-skill:confirm', 'project:create']
export const PRODUCT_PORTAL_PERMISSIONS = ['portal:product', 'product:pipeline:create', 'flow:pipeline:match', 'flow:pipeline:create']
export const PIPELINE_WORKBENCH_PERMISSIONS = ['flow:pipeline:list']
export const PIPELINE_PAGE_PERMISSIONS = [...PRODUCT_PORTAL_PERMISSIONS, ...PIPELINE_WORKBENCH_PERMISSIONS]

const PORTAL_PATH_ALIASES: Record<string, string> = {
  '/developer': '/project/access',
  '/product': '/pipeline/development',
  '/pipeline/requirement': '/pipeline/development',
  '/pipeline/advanced': '/pipeline/development',
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

export const hasAnyPermissionForUser = (user: User | null | undefined, permissions: string[]) => {
  if (!user) return false
  const expanded = expandPermissions(user.permissions)
  if (user.isSuper || expanded.includes('*')) return true
  return permissions.some((permission) => {
    const normalized = normalizePermission(permission)
    return expanded.includes(normalized) || expanded.includes(normalized.replace(/:/g, '_'))
  })
}

export const canUseDeveloperPortal = (user: User | null | undefined) =>
  hasAnyPermissionForUser(user, DEVELOPER_PORTAL_PERMISSIONS)

export const canUseProductPortal = (user: User | null | undefined) =>
  hasAnyPermissionForUser(user, PRODUCT_PORTAL_PERMISSIONS)

export const canUsePipelineWorkbench = (user: User | null | undefined) =>
  hasAnyPermissionForUser(user, PIPELINE_WORKBENCH_PERMISSIONS)

export const normalizePortalPath = (path: string | null | undefined) => {
  if (!path) return null
  const pathname = String(path).split('?')[0].split('#')[0]
  return PORTAL_PATH_ALIASES[pathname] || pathname
}

const portalStorageKey = (user: User | null | undefined) => {
  if (!user?.adminId) return null
  return `lastPortalPath:${user.tenantId || 0}:${user.adminId}`
}

const getStorage = () => {
  try {
    return typeof window !== 'undefined' ? window.localStorage : globalThis.localStorage
  } catch {
    return null
  }
}

const isPortalPathAllowed = (user: User | null | undefined, path: string | null) => {
  if (!path) return false
  if (path === '/project/access') return canUseDeveloperPortal(user)
  if (path === '/pipeline/development') return canUseProductPortal(user) || canUsePipelineWorkbench(user)
  return false
}

export const getLastPortalPath = (user: User | null | undefined) => {
  const key = portalStorageKey(user)
  const storage = getStorage()
  if (!key || !storage) return null

  const normalized = normalizePortalPath(storage.getItem(key))
  if (!isPortalPathAllowed(user, normalized)) {
    storage.removeItem(key)
    return null
  }
  return normalized
}

export const saveLastPortalPath = (user: User | null | undefined, path: string) => {
  const key = portalStorageKey(user)
  const storage = getStorage()
  const normalized = normalizePortalPath(path)
  if (!key || !storage) return null
  if (!normalized) return null
  if (!isPortalPathAllowed(user, normalized)) {
    storage.removeItem(key)
    return null
  }
  storage.setItem(key, normalized)
  return normalized
}

export const resolveLandingPath = (user: User | null | undefined) => {
  const developer = canUseDeveloperPortal(user)
  const product = canUseProductPortal(user)
  const pipeline = canUsePipelineWorkbench(user)
  if (developer && (product || pipeline)) return getLastPortalPath(user) || '/portal-select'
  if (product) return '/pipeline/development'
  if (pipeline) return '/pipeline/development'
  if (developer) return '/project/access'
  return '/project/create'
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user: { ...user, permissions: expandPermissions(user.permissions) } }),
      logout: () => set({ token: null, user: null }),
      hasPermission: (permission) => hasAnyPermissionForUser(get().user, [permission]),
      hasAnyPermission: (permissions) => {
        if (!permissions.length) return true
        return hasAnyPermissionForUser(get().user, permissions)
      },
    }),
    {
      name: 'auth-storage',
    }
  )
)
