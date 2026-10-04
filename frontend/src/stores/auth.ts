import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'

export interface AuthUser {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_verified: boolean
  tenant_id: string | null
  tenant_role: string | null
  platform_role: string | null
}

interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: AuthUser
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<AuthUser | null>(null)

  // Restore user from localStorage on app boot
  const storedUser = localStorage.getItem('current_user')
  if (storedUser) {
    try { user.value = JSON.parse(storedUser) } catch { /* ignore */ }
  }

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isPlatformUser = computed(() => !!user.value?.platform_role)

  async function login(email: string, password: string): Promise<void> {
    const { data } = await api.post<LoginResponse>('/auth/login', {
      email, password,
    })
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('current_user', JSON.stringify(data.user))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
  }

  return { token, user, isAuthenticated, isPlatformUser, login, logout }
})