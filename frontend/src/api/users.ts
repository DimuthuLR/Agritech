import { api } from './client'

export type TenantRole =
  | 'viewer'
  | 'operator'
  | 'agronomist'
  | 'tenant_admin'

export interface TenantUser {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_verified: boolean
  tenant_id: string | null
  tenant_role: TenantRole | null
  created_at: string
  last_login_at: string | null
}

export interface CreateUserInput {
  email: string
  password: string
  full_name?: string | null
  role: TenantRole
}

export interface UpdateUserInput {
  full_name?: string | null
  role?: TenantRole
  is_active?: boolean
}

export const usersApi = {
  async list(): Promise<TenantUser[]> {
    const { data } = await api.get<TenantUser[]>('/users')
    return data
  },

  async create(input: CreateUserInput): Promise<TenantUser> {
    const { data } = await api.post<TenantUser>('/users', input)
    return data
  },

  async update(id: string, patch: UpdateUserInput): Promise<TenantUser> {
    const { data } = await api.patch<TenantUser>(`/users/${id}`, patch)
    return data
  },
}

// Human-friendly labels for roles
export const ROLE_LABELS: Record<TenantRole, string> = {
  viewer: 'Viewer',
  operator: 'Operator',
  agronomist: 'Agronomist',
  tenant_admin: 'Tenant Admin',
}

export const ROLE_HINTS: Record<TenantRole, string> = {
  viewer: 'Read-only access to plots, sensors, and reports',
  operator: 'Can approve tasks and manage devices',
  agronomist: 'Can do everything operators can, plus approve chemical treatments',
  tenant_admin: 'Full access — can invite users and change settings',
}