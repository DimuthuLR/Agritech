<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { api } from '../../api/client'
import { useRouter } from 'vue-router'
import {
  Users, Sprout, Activity, Server, Loader2,
} from 'lucide-vue-next'

interface PlatformStats {
  tenants_total: number
  tenants_active: number
  tenants_suspended: number
  users_total: number
  users_active: number
  farms_total: number
  plots_total: number
  devices_total: number
  diagnoses_total: number
  diagnoses_last_30d: number
  diagnoses_today: number
}

interface TenantSummary {
  id: string
  name: string
  slug: string
  region: string
  is_active: boolean
  created_at: string
  user_count: number
  farm_count: number
  plot_count: number
  diagnoses_last_30d: number
}

const stats = ref<PlatformStats | null>(null)
const tenants = ref<TenantSummary[]>([])
const loading = ref(true)
const busyId = ref<string | null>(null)
const error = ref<string | null>(null)
const router = useRouter()

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, t] = await Promise.all([
      api.get<PlatformStats>('/platform/stats'),
      api.get<TenantSummary[]>('/platform/tenants'),
    ])
    stats.value = s.data
    tenants.value = t.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load platform data'
  } finally {
    loading.value = false
  }
}

async function toggleSuspend(t: TenantSummary) {
  const action = t.is_active ? 'suspend' : 'reactivate'
  if (action === 'suspend') {
    const reason = prompt(`Reason for suspending ${t.name}:`)
    if (!reason || reason.length < 3) return
    busyId.value = t.id
    try {
      await api.post(`/platform/tenants/${t.id}/suspend`, { reason })
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed')
    } finally {
      busyId.value = null
    }
  } else {
    busyId.value = t.id
    try {
      await api.post(`/platform/tenants/${t.id}/reactivate`)
      await load()
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed')
    } finally {
      busyId.value = null
    }
  }
}

onMounted(load)

const activeCount = computed(() => stats.value?.tenants_active ?? 0)
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl font-semibold">Platform</h1>
        <p class="text-sm text-muted mt-1">
          Cross-tenant operations · {{ activeCount }} active tenants
        </p>
      </div>
      <button
        class="btn-ghost text-sm"
        @click="router.push({ name: 'platform-sessions' })"
      >
        Support sessions →
      </button>
    </div>

    <div v-if="loading" class="text-muted flex items-center gap-2">
      <Loader2 :size="16" class="animate-spin" /> Loading…
    </div>

    <div v-else-if="error" class="card text-danger">{{ error }}</div>

    <template v-else-if="stats">
      <!-- Stat grid -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
        <div class="card">
          <div class="text-xs uppercase tracking-wide text-muted flex items-center gap-2">
            <Server :size="14" /> Tenants
          </div>
          <div class="text-2xl font-semibold mt-2">{{ stats.tenants_total }}</div>
          <div class="text-xs text-muted mt-1">
            {{ stats.tenants_active }} active · {{ stats.tenants_suspended }} suspended
          </div>
        </div>
        <div class="card">
          <div class="text-xs uppercase tracking-wide text-muted flex items-center gap-2">
            <Users :size="14" /> Users
          </div>
          <div class="text-2xl font-semibold mt-2">{{ stats.users_total }}</div>
          <div class="text-xs text-muted mt-1">
            {{ stats.users_active }} active
          </div>
        </div>
        <div class="card">
          <div class="text-xs uppercase tracking-wide text-muted flex items-center gap-2">
            <Sprout :size="14" /> Plots
          </div>
          <div class="text-2xl font-semibold mt-2">{{ stats.plots_total }}</div>
          <div class="text-xs text-muted mt-1">
            {{ stats.farms_total }} farms · {{ stats.devices_total }} devices
          </div>
        </div>
        <div class="card">
          <div class="text-xs uppercase tracking-wide text-muted flex items-center gap-2">
            <Activity :size="14" /> Diagnoses
          </div>
          <div class="text-2xl font-semibold mt-2">{{ stats.diagnoses_today }}</div>
          <div class="text-xs text-muted mt-1">
            today · {{ stats.diagnoses_last_30d }} last 30d · {{ stats.diagnoses_total }} total
          </div>
        </div>
      </div>

      <!-- Tenant table -->
      <div class="card p-0 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-card-hover text-muted text-xs uppercase tracking-wide">
            <tr>
              <th class="text-left px-4 py-2">Tenant</th>
              <th class="text-left px-4 py-2 hidden md:table-cell">Region</th>
              <th class="text-right px-4 py-2 hidden md:table-cell">Users</th>
              <th class="text-right px-4 py-2 hidden md:table-cell">Farms</th>
              <th class="text-right px-4 py-2 hidden md:table-cell">Plots</th>
              <th class="text-right px-4 py-2 hidden lg:table-cell">Diag 30d</th>
              <th class="text-left px-4 py-2">Status</th>
              <th class="text-right px-4 py-2">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            <tr v-for="t in tenants" :key="t.id">
              <td class="px-4 py-3">
                <div class="font-medium">{{ t.name }}</div>
                <div class="text-xs text-muted">{{ t.slug }}</div>
              </td>
              <td class="px-4 py-3 text-muted hidden md:table-cell">{{ t.region }}</td>
              <td class="px-4 py-3 text-right tabular-nums hidden md:table-cell">{{ t.user_count }}</td>
              <td class="px-4 py-3 text-right tabular-nums hidden md:table-cell">{{ t.farm_count }}</td>
              <td class="px-4 py-3 text-right tabular-nums hidden md:table-cell">{{ t.plot_count }}</td>
              <td class="px-4 py-3 text-right tabular-nums hidden lg:table-cell">{{ t.diagnoses_last_30d }}</td>
              <td class="px-4 py-3">
                <span v-if="t.is_active" class="pill-success text-xs">Active</span>
                <span v-else class="pill-danger text-xs">Suspended</span>
              </td>
              <td class="px-4 py-3 text-right">
                <button
                  class="btn-ghost text-xs py-1 px-3"
                  :disabled="busyId === t.id"
                  @click="toggleSuspend(t)"
                >
                  <Loader2 v-if="busyId === t.id" :size="12" class="animate-spin inline" />
                  <template v-else>
                    {{ t.is_active ? 'Suspend' : 'Reactivate' }}
                  </template>
                </button>
              </td>
            </tr>
            <tr v-if="tenants.length === 0">
              <td colspan="8" class="text-center text-muted py-8">No tenants.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>