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

interface ImpersonationState {
  sessionId: string
  impersonationToken: string
  targetUser: AuthUser
  originalToken: string
  originalUser: AuthUser
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<AuthUser | null>(null)
  const features = ref<Record<string, boolean> | null>(null)
  const impersonation = ref<ImpersonationState | null>(null)

  // --- Restore from localStorage on boot ---
  const storedUser = localStorage.getItem('current_user')
  if (storedUser) {
    try { user.value = JSON.parse(storedUser) } catch { /* ignore */ }
  }
  const storedFeatures = localStorage.getItem('tenant_features')
  if (storedFeatures) {
    try { features.value = JSON.parse(storedFeatures) } catch { /* ignore */ }
  }
  const storedImpersonation = localStorage.getItem('impersonation_state')
  if (storedImpersonation) {
    try {
      impersonation.value = JSON.parse(storedImpersonation)
      if (impersonation.value) {
        token.value = impersonation.value.impersonationToken
        user.value = impersonation.value.targetUser
      }
    } catch { /* ignore */ }
  }

  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isPlatformUser = computed(() => !!user.value?.platform_role)
  const isImpersonating = computed(() => !!impersonation.value)

  function hasFeature(key: string): boolean {
    if (features.value === null) return true
    return features.value[key] !== false
  }

  async function loadFeatures(): Promise<void> {
    try {
      const { data } = await api.get<Record<string, boolean>>('/auth/me/features')
      features.value = data
      localStorage.setItem('tenant_features', JSON.stringify(data))
    } catch { /* keep last known map */ }
  }

  async function login(email: string, password: string): Promise<void> {
    const { data } = await api.post<LoginResponse>('/auth/login', { email, password })
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('current_user', JSON.stringify(data.user))
    await loadFeatures()
  }

  function logout() {
    token.value = null
    user.value = null
    features.value = null
    impersonation.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_user')
    localStorage.removeItem('tenant_features')
    localStorage.removeItem('impersonation_state')
  }

  /**
   * Swap into an impersonated session. Called after a platform admin
   * successfully creates a support session on the backend.
   */
  function startImpersonation(payload: {
    sessionId: string
    impersonationToken: string
    targetUser: AuthUser
  }): void {
    if (!token.value || !user.value) {
      throw new Error('Cannot impersonate without an active session')
    }
    impersonation.value = {
      sessionId: payload.sessionId,
      impersonationToken: payload.impersonationToken,
      targetUser: payload.targetUser,
      originalToken: token.value,
      originalUser: user.value,
    }
    token.value = payload.impersonationToken
    user.value = payload.targetUser
    localStorage.setItem('access_token', payload.impersonationToken)
    localStorage.setItem('current_user', JSON.stringify(payload.targetUser))
    localStorage.setItem('impersonation_state', JSON.stringify(impersonation.value))
  }

  /**
   * End the current impersonation session.
   * Calls the API with the ORIGINAL token (the interceptor overwrites
   * the auth header, so we temporarily swap the localStorage value),
   * then restores the platform admin's session.
   */
  async function endImpersonation(): Promise<void> {
    const imp = impersonation.value
    if (!imp) return

    const savedToken = localStorage.getItem('access_token')
    try {
      localStorage.setItem('access_token', imp.originalToken)
      await api.post(`/platform/support-sessions/${imp.sessionId}/end`)
    } catch {
      // Even on failure, restore locally — a stale server-side session
      // is harmless and can be ended later from the sessions page.
    } finally {
      localStorage.setItem('access_token', savedToken || imp.originalToken)
    }

    token.value = imp.originalToken
    user.value = imp.originalUser
    impersonation.value = null
    localStorage.setItem('access_token', imp.originalToken)
    localStorage.setItem('current_user', JSON.stringify(imp.originalUser))
    localStorage.removeItem('impersonation_state')
  }

  return {
    token,
    user,
    features,
    impersonation,
    isAuthenticated,
    isPlatformUser,
    isImpersonating,
    hasFeature,
    loadFeatures,
    login,
    logout,
    startImpersonation,
    endImpersonation,
  }
})