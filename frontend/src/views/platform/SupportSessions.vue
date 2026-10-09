<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { api } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import {
  Loader2, Play, Square, X, Search,
} from 'lucide-vue-next'

interface Tenant {
  id: string
  name: string
  slug: string
  is_active: boolean
}

interface TenantUser {
  id: string
  email: string
  full_name: string | null
  tenant_role: string | null
  is_active: boolean
}

interface SupportSession {
  id: string
  platform_user_id: string | null
  target_user_id: string | null
  target_tenant_id: string
  reason: string
  ticket_reference: string | null
  started_at: string
  ended_at: string | null
  ip_address: string | null
}

interface StartResponse {
  session: SupportSession
  access_token: string
  expires_in: number
  impersonated_user: {
    id: string
    email: string
    full_name: string | null
    tenant_id: string | null
    tenant_role: string | null
  }
}

const auth = useAuthStore()

const sessions = ref<SupportSession[]>([])
const tenants = ref<Tenant[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const busy = ref<string | null>(null)

// Modal state
const showModal = ref(false)
const selectedTenantId = ref<string>('')
const tenantUsers = ref<TenantUser[]>([])
const usersLoading = ref(false)
const userSearch = ref('')
const selectedUserId = ref<string>('')
const reason = ref('')
const ticketRef = ref('')
const starting = ref(false)

const filteredUsers = computed(() => {
  const q = userSearch.value.toLowerCase().trim()
  if (!q) return tenantUsers.value
  return tenantUsers.value.filter(
    (u) => u.email.toLowerCase().includes(q) ||
           (u.full_name || '').toLowerCase().includes(q),
  )
})

async function loadSessions() {
  loading.value = true
  error.value = null
  try {
    const [s, t] = await Promise.all([
      api.get<SupportSession[]>('/platform/support-sessions'),
      api.get<Tenant[]>('/platform/tenants'),
    ])
    sessions.value = s.data
    tenants.value = t.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load'
  } finally {
    loading.value = false
  }
}

async function loadTenantUsers(tenantId: string) {
  tenantUsers.value = []
  if (!tenantId) return
  usersLoading.value = true
  try {
    const { data } = await api.get<TenantUser[]>(`/platform/tenants/${tenantId}/users`)
    tenantUsers.value = data
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed to load users')
  } finally {
    usersLoading.value = false
  }
}

function openModal() {
  showModal.value = true
  selectedTenantId.value = ''
  tenantUsers.value = []
  selectedUserId.value = ''
  reason.value = ''
  ticketRef.value = ''
  userSearch.value = ''
}

function closeModal() {
  showModal.value = false
}

async function startSession() {
  if (!selectedUserId.value || reason.value.length < 3) return
  starting.value = true
  try {
    const { data } = await api.post<StartResponse>(
      '/platform/support-sessions',
      {
        target_user_id: selectedUserId.value,
        reason: reason.value,
        ticket_reference: ticketRef.value || null,
      },
    )
    // Swap the local session into impersonation mode
    auth.startImpersonation({
      sessionId: data.session.id,
      impersonationToken: data.access_token,
      targetUser: {
        id: data.impersonated_user.id,
        email: data.impersonated_user.email,
        full_name: data.impersonated_user.full_name,
        is_active: true,
        is_verified: true,
        tenant_id: data.impersonated_user.tenant_id,
        tenant_role: data.impersonated_user.tenant_role,
        platform_role: null,
      },
    })
    closeModal()
    // Navigate into the tenant experience
    window.location.href = '/dashboard'
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed to start session')
  } finally {
    starting.value = false
  }
}

async function endSession(s: SupportSession) {
  if (!confirm('End this support session? Any impersonation tokens issued for it will stop working.')) return
  busy.value = s.id
  try {
    await api.post(`/platform/support-sessions/${s.id}/end`)
    await loadSessions()
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Failed')
  } finally {
    busy.value = null
  }
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString()
}

function duration(s: SupportSession) {
  const end = s.ended_at ? new Date(s.ended_at) : new Date()
  const start = new Date(s.started_at)
  const mins = Math.round((end.getTime() - start.getTime()) / 60000)
  if (mins < 1) return '<1 min'
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return `${h}h ${m}m`
}

onMounted(loadSessions)
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl font-semibold">Support Sessions</h1>
        <p class="text-sm text-muted mt-1">
          Audited impersonation · every session is logged
        </p>
      </div>
      <button class="btn-primary text-sm" @click="openModal">
        <Play :size="14" /> Start session
      </button>
    </div>

    <div v-if="loading" class="text-muted flex items-center gap-2">
      <Loader2 :size="16" class="animate-spin" /> Loading…
    </div>
    <div v-else-if="error" class="card text-danger">{{ error }}</div>

    <div v-else class="card p-0 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-card-hover text-muted text-xs uppercase tracking-wide">
          <tr>
            <th class="text-left px-4 py-2">Started</th>
            <th class="text-left px-4 py-2">Target</th>
            <th class="text-left px-4 py-2 hidden md:table-cell">Reason</th>
            <th class="text-left px-4 py-2 hidden lg:table-cell">Duration</th>
            <th class="text-left px-4 py-2">Status</th>
            <th class="text-right px-4 py-2">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          <tr v-for="s in sessions" :key="s.id">
            <td class="px-4 py-3 text-xs text-muted">{{ fmtDate(s.started_at) }}</td>
            <td class="px-4 py-3">
              <div class="text-xs">user {{ s.target_user_id?.slice(0, 8) }}</div>
              <div class="text-xs text-muted">tenant {{ s.target_tenant_id.slice(0, 8) }}</div>
            </td>
            <td class="px-4 py-3 text-xs text-muted hidden md:table-cell max-w-xs truncate">
              {{ s.reason }}
            </td>
            <td class="px-4 py-3 text-xs hidden lg:table-cell">{{ duration(s) }}</td>
            <td class="px-4 py-3">
              <span v-if="s.ended_at" class="pill-muted text-xs">Ended</span>
              <span v-else class="pill-warning text-xs">Active</span>
            </td>
            <td class="px-4 py-3 text-right">
              <button
                v-if="!s.ended_at"
                class="btn-ghost text-xs py-1 px-3 text-danger"
                :disabled="busy === s.id"
                @click="endSession(s)"
              >
                <Loader2 v-if="busy === s.id" :size="12" class="animate-spin inline" />
                <template v-else>
                  <Square :size="12" class="inline" /> End
                </template>
              </button>
            </td>
          </tr>
          <tr v-if="sessions.length === 0">
            <td colspan="6" class="text-center text-muted py-8">No sessions yet.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal: start new session -->
    <div
      v-if="showModal"
      class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      @click.self="closeModal"
    >
      <div class="bg-card border border-border rounded-md w-full max-w-lg p-5 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">Start support session</h2>
          <button class="text-muted hover:text-text" @click="closeModal">
            <X :size="18" />
          </button>
        </div>

        <!-- Tenant picker -->
        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">Tenant</label>
          <select
            v-model="selectedTenantId"
            class="input w-full"
            @change="loadTenantUsers(selectedTenantId)"
          >
            <option value="">— select a tenant —</option>
            <option v-for="t in tenants" :key="t.id" :value="t.id">
              {{ t.name }} {{ t.is_active ? '' : '(suspended)' }}
            </option>
          </select>
        </div>

        <!-- User picker -->
        <div v-if="selectedTenantId">
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">
            Target user
          </label>
          <div class="relative mb-2">
            <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              v-model="userSearch"
              type="text"
              placeholder="Search by email or name…"
              class="input w-full pl-9"
            />
          </div>
          <div v-if="usersLoading" class="text-muted text-xs flex items-center gap-2">
            <Loader2 :size="12" class="animate-spin" /> Loading users…
          </div>
          <div v-else class="max-h-48 overflow-y-auto border border-border rounded-sm">
            <button
              v-for="u in filteredUsers"
              :key="u.id"
              type="button"
              class="w-full text-left px-3 py-2 text-sm hover:bg-card-hover
                     border-b border-border last:border-b-0"
              :class="{ 'bg-accent-soft text-accent': selectedUserId === u.id }"
              @click="selectedUserId = u.id"
            >
              <div>{{ u.email }}</div>
              <div class="text-xs text-muted">
                {{ u.full_name || '—' }}
                <span v-if="u.tenant_role"> · {{ u.tenant_role }}</span>
              </div>
            </button>
            <div v-if="filteredUsers.length === 0" class="p-3 text-xs text-muted">
              No matching users.
            </div>
          </div>
        </div>

        <!-- Reason -->
        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">
            Reason (required, logged)
          </label>
          <textarea
            v-model="reason"
            rows="2"
            class="input w-full"
            placeholder="e.g. Debugging sensor sync issue reported by customer"
          />
        </div>

        <!-- Ticket ref -->
        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">
            Ticket reference (optional)
          </label>
          <input v-model="ticketRef" type="text" class="input w-full" placeholder="SUP-1234" />
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button class="btn-ghost text-sm" @click="closeModal">Cancel</button>
          <button
            class="btn-primary text-sm"
            :disabled="!selectedUserId || reason.length < 3 || starting"
            @click="startSession"
          >
            <Loader2 v-if="starting" :size="14" class="animate-spin inline" />
            <Play v-else :size="14" class="inline" />
            Start & impersonate
          </button>
        </div>
      </div>
    </div>
  </div>
</template>