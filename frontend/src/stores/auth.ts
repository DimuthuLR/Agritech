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

  // Feature map: { diagnosis: true, finance: false, ... }
  // null means "not loaded yet" — treat as fail-open (everything visible).
  const features = ref<Record<string, boolean> | null>(null)

  // Restore user from localStorage on app boot
  const storedUser = localStorage.getItem('current_user')
  if (storedUser) {
    try { user.value = JSON.parse(storedUser) } catch { /* ignore */ }
  }

  // Restore features from localStorage on app boot
  const storedFeatures = localStorage.getItem('tenant_features')
  if (storedFeatures) {
    try { features.value = JSON.parse(storedFeatures) } catch { /* ignore */ }
  }

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isPlatformUser = computed(() => !!user.value?.platform_role)

  /**
   * Return true if the tenant has the given feature enabled.
   * Before the first successful load, this fails open (returns true)
   * so nothing flickers off during the initial render.
   */
  function hasFeature(key: string): boolean {
    if (features.value === null) return true
    // Unknown key → treat as enabled (matches backend default)
    return features.value[key] !== false
  }

  async function loadFeatures(): Promise<void> {
    try {
      const { data } = await api.get<Record<string, boolean>>(
        '/auth/me/features',
      )
      features.value = data
      localStorage.setItem('tenant_features', JSON.stringify(data))
    } catch {
      // Network failure or 5xx — keep the last known map.
      // Better to show features that might be off than to hide everything.
    }
  }

  async function login(email: string, password: string): Promise<void> {
    const { data } = await api.post<LoginResponse>('/auth/login', {
      email, password,
    })
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('current_user', JSON.stringify(data.user))
    // Load this tenant's feature map immediately after login.
    await loadFeatures()
  }

  function logout() {
    token.value = null
    user.value = null
    features.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    localStorage.removeItem('tenant_features')
  }

  return {
    token,
    user,
    features,
    isAuthenticated,
    isPlatformUser,
    hasFeature,
    loadFeatures,
    login,
    logout,
  }
})