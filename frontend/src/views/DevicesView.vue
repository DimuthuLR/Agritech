<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { devicesApi } from '../api/devices'
import type { Device } from '../types/device'
import {
  Loader2, Cpu, Wifi, WifiOff, Battery, Activity,
  Play, Search, X, AlertCircle, Signal,
} from 'lucide-vue-next'

const devices = ref<Device[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')
const kindFilter = ref<string>('')
const statusFilter = ref<string>('')

const showModal = ref(false)
const activeDevice = ref<Device | null>(null)
const actionChoice = ref('irrigation.start')
const actionParams = ref<string>('{}')
const sending = ref(false)
const sendResult = ref<string | null>(null)

const ONLINE_THRESHOLD_SEC = 5 * 60  // 5 minutes

function isOnline(d: Device): boolean {
  if (!d.last_seen_at) return false
  const seen = new Date(d.last_seen_at).getTime()
  return (Date.now() - seen) / 1000 < ONLINE_THRESHOLD_SEC
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  const now = Date.now()
  const s = Math.floor((now - then) / 1000)
  if (s < 60) return 'just now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return `${Math.floor(d / 30)}mo ago`
}

function fmtUptime(sec: number | null): string {
  if (sec === null || sec === 0) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}


function statusLabel(d: Device): string {
  if (!d.is_active) return 'Inactive'
  return isOnline(d) ? 'Online' : 'Offline'
}

function statusClass(d: Device): string {
  if (!d.is_active) return 'text-muted'
  return isOnline(d) ? 'text-success' : 'text-danger'
}

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  return devices.value.filter((d) => {
    if (q && !d.serial.toLowerCase().includes(q) &&
        !(d.model || '').toLowerCase().includes(q)) {
      return false
    }
    if (kindFilter.value && d.kind !== kindFilter.value) return false
    if (statusFilter.value === 'online' && !isOnline(d)) return false
    if (statusFilter.value === 'offline' && isOnline(d)) return false
    return true
  })
})

const counts = computed(() => {
  let online = 0
  let offline = 0
  for (const d of devices.value) {
    if (isOnline(d)) online++
    else offline++
  }
  return { online, offline }
})

async function load() {
  loading.value = true
  error.value = null
  try {
    devices.value = await devicesApi.list()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load devices'
  } finally {
    loading.value = false
  }
}

function openCommand(d: Device) {
  activeDevice.value = d
  actionChoice.value = 'irrigation.start'
  actionParams.value = '{}'
  sendResult.value = null
  showModal.value = true
}

async function sendCommand() {
  if (!activeDevice.value) return
  sending.value = true
  sendResult.value = null
  try {
    let params: Record<string, unknown> = {}
    try { params = JSON.parse(actionParams.value) } catch {
      sendResult.value = 'Invalid JSON in params'
      sending.value = false
      return
    }
    const resp = await devicesApi.sendTestCommand(
      activeDevice.value.id,
      actionChoice.value,
      params,
    )
    sendResult.value = `Sent ${resp.cmd_id} to ${resp.topic}`
  } catch (e: any) {
    sendResult.value = e?.response?.data?.detail || 'Failed to send'
  } finally {
    sending.value = false
  }
}

onMounted(load)

// Refresh every 15s so uptime/last-seen stay fresh
setInterval(load, 15000)
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">

    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="page-title">Devices</h1>
        <p class="page-subtitle">
          {{ counts.online }} online · {{ counts.offline }} offline
        </p>
      </div>
      <button class="btn-ghost text-sm" @click="load" :disabled="loading">
        <Loader2 v-if="loading" :size="14" class="animate-spin" />
        Refresh
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3">
      <div class="relative flex-1 min-w-[200px]">
        <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          v-model="search"
          type="text"
          placeholder="Search by serial or model…"
          class="input pl-9"
        />
      </div>
      <select v-model="kindFilter" class="input w-40">
        <option value="">All kinds</option>
        <option value="sensor">Sensor</option>
        <option value="actuator">Actuator</option>
        <option value="gateway">Gateway</option>
      </select>
      <select v-model="statusFilter" class="input w-40">
        <option value="">All status</option>
        <option value="online">Online</option>
        <option value="offline">Offline</option>
      </select>
    </div>

    <!-- Loading / error / empty -->
    <div v-if="loading && devices.length === 0"
         class="text-muted flex items-center gap-2">
      <Loader2 :size="16" class="animate-spin" /> Loading devices…
    </div>

    <div v-else-if="error" class="card text-danger">{{ error }}</div>

    <div v-else-if="filtered.length === 0" class="card text-center py-12">
      <Cpu :size="32" :stroke-width="1.5" class="mx-auto text-muted mb-3" />
      <h3 class="font-semibold text-lg">No devices</h3>
      <p class="text-sm text-muted mt-1.5">
        {{ devices.length === 0
            ? 'Register a device or run the simulator to get started.'
            : 'No devices match the current filters.' }}
      </p>
    </div>

    <!-- Device grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div v-for="d in filtered" :key="d.id" class="card">
        <div class="flex items-start justify-between gap-3 mb-4">
          <div class="min-w-0">
            <div class="font-mono text-sm font-semibold truncate">
              {{ d.serial }}
            </div>
            <div class="text-xs text-muted mt-1 flex items-center gap-2 flex-wrap">
              <span v-if="d.model">{{ d.model }}</span>
              <span v-if="d.chip_type">· {{ d.chip_type }}</span>
              <span v-if="d.hw_version">· {{ d.hw_version }}</span>
            </div>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <component
              :is="isOnline(d) ? Wifi : WifiOff"
              :size="14"
              :class="statusClass(d)"
              :stroke-width="2"
            />
            <span :class="['text-xs font-medium', statusClass(d)]">
              {{ statusLabel(d) }}
            </span>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-3 py-3 border-t border-b border-border">
          <div>
            <div class="text-[10px] uppercase tracking-wide text-muted flex items-center gap-1">
              <Activity :size="10" /> Uptime
            </div>
            <div class="text-sm font-medium tabular-nums mt-1">
              {{ fmtUptime(d.uptime_sec) }}
            </div>
          </div>
          <div>
            <div class="text-[10px] uppercase tracking-wide text-muted flex items-center gap-1">
              <Signal :size="10" /> RSSI
            </div>
            <div class="text-sm font-medium tabular-nums mt-1">
              {{ d.rssi_dbm !== null ? `${d.rssi_dbm} dBm` : '—' }}
            </div>
          </div>
          <div>
            <div class="text-[10px] uppercase tracking-wide text-muted flex items-center gap-1">
              <Battery :size="10" /> Battery
            </div>
            <div class="text-sm font-medium tabular-nums mt-1">
              {{ d.battery_v !== null ? `${d.battery_v.toFixed(2)}V` : '—' }}
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between mt-3 gap-3">
          <div class="text-xs text-muted">
            Last seen: {{ relativeTime(d.last_seen_at) }}
          </div>
          <button
            class="btn-ghost text-xs py-1 px-3"
            @click="openCommand(d)"
          >
            <Play :size="11" /> Test command
          </button>
        </div>

        <div
          v-if="d.last_error_code"
          class="mt-3 text-xs text-danger bg-danger/10 rounded-sm px-2 py-1.5 flex items-start gap-1.5"
        >
          <AlertCircle :size="12" class="shrink-0 mt-0.5" />
          <span>{{ d.last_error_code }}: {{ d.last_error_message }}</span>
        </div>
      </div>
    </div>

    <!-- Command modal -->
    <div
      v-if="showModal && activeDevice"
      class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      @click.self="showModal = false"
    >
      <div class="bg-card border border-border rounded w-full max-w-md p-5 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">Send test command</h2>
          <button class="text-muted hover:text-text" @click="showModal = false">
            <X :size="18" />
          </button>
        </div>

        <div class="text-xs text-muted font-mono">
          {{ activeDevice.serial }}
        </div>

        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">
            Action
          </label>
          <select v-model="actionChoice" class="input w-full">
            <option value="irrigation.start">irrigation.start</option>
            <option value="irrigation.stop">irrigation.stop</option>
            <option value="valve.open">valve.open</option>
            <option value="valve.close">valve.close</option>
            <option value="light.on">light.on</option>
            <option value="light.off">light.off</option>
            <option value="relay.pulse">relay.pulse</option>
            <option value="reboot">reboot</option>
          </select>
        </div>

        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">
            Params (JSON)
          </label>
          <textarea
            v-model="actionParams"
            rows="2"
            class="input w-full font-mono text-xs"
            placeholder='{"duration_sec": 60}'
          />
        </div>

        <div
          v-if="sendResult"
          class="text-xs bg-card-hover rounded-sm px-3 py-2"
        >
          {{ sendResult }}
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button class="btn-ghost text-sm" @click="showModal = false">Close</button>
          <button
            class="btn-primary text-sm"
            :disabled="sending"
            @click="sendCommand"
          >
            <Loader2 v-if="sending" :size="14" class="animate-spin" />
            <Play v-else :size="14" />
            Send
          </button>
        </div>
      </div>
    </div>

  </div>
</template>