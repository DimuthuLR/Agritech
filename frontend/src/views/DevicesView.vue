<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { devicesApi } from '../api/devices'
import { api } from '../api/client'
import type { Device, DeviceEvent } from '../types/device'
import { usePlotsStore } from '../stores/plots'
import { useAuthStore } from '../stores/auth'
import {
  Loader2, Cpu, Wifi, WifiOff, Battery, Activity,
  Play, Search, X, AlertCircle, CheckCircle,
  Droplets, Thermometer, Server, Power, PenBox, ShieldAlert
} from 'lucide-vue-next'

const devices = ref<Device[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')
const statusFilter = ref<string>('')

const actuatorStates = ref<Record<string, { pump: boolean, valve: boolean }>>({})

const showModal = ref(false)
const activeDevice = ref<Device | null>(null)
const actionChoice = ref('irrigation.start')
const actionParams = ref<string>('{}')
const sending = ref(false)
const sendResult = ref<string | null>(null)
const isOverride = ref(false)

const showAssignModal = ref(false)
const assigningDevice = ref<Device | null>(null)
const selectedPlotId = ref<string>('')
const assigning = ref(false)

const expandedDeviceId = ref<string | null>(null)
const deviceEvents = ref<Record<string, DeviceEvent[]>>({})
const loadingEvents = ref<string | null>(null)

const plotsStore = usePlotsStore()
const authStore = useAuthStore()

const ONLINE_THRESHOLD_SEC = 5 * 60

const canEdit = computed(() => {
  const role = authStore.user?.tenant_role
  if (!role) return false
  const normalizedRole = role.toLowerCase().replace(/[\s_]/g, '')
  return normalizedRole === 'tenantadmin' || normalizedRole === 'operator'
})

// Watch for modal opening to set the smartest default action
watch(showModal, (val) => {
  if (val && activeDevice.value && activeDevice.value.kind === 'actuator') {
    const state = actuatorStates.value[activeDevice.value.id]
    if (state?.pump) {
      actionChoice.value = 'irrigation.stop'
    } else {
      actionChoice.value = 'irrigation.start'
    }
  }
})

function getControlMode(d: Device): 'auto' | 'manual' {
  return d.metadata?.control_mode === 'auto' ? 'auto' : 'manual'
}

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
  return `${d}d ago`
}

function fmtUptime(sec: number | null): string {
  if (sec === null || sec === 0) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function getPlotName(plotId: string | null): string {
  if (!plotId) return 'Unassigned'
  const plot = plotsStore.plots.find(p => p.id === plotId)
  return plot ? plot.name : 'Unknown Plot'
}

function getDeviceName(d: Device): string {
  if (d.kind === 'gateway') return 'Main Controller (Hub)'
  const plotName = getPlotName(d.plot_id)
  if (d.kind === 'sensor') return `${plotName} Sensor`
  if (d.kind === 'actuator') return `${plotName} Controls`
  return d.serial
}

function statusClass(d: Device): string {
  if (!d.is_active) return 'text-muted'
  return isOnline(d) ? 'text-success' : 'text-danger'
}

function eventTone(e: DeviceEvent): string {
  if (e.event_type === 'error' || e.event_type === 'manual_override') return 'text-danger'
  if (e.status === 'ok') return 'text-success'
  if (e.status === 'failed' || e.status === 'rejected') return 'text-danger'
  return 'text-muted'
}

function eventIcon(e: DeviceEvent): any {
  if (e.event_type === 'manual_override') return ShieldAlert
  return e.event_type === 'error' ? AlertCircle : CheckCircle
}

const filteredDevices = computed(() => {
  const q = search.value.toLowerCase().trim()
  return devices.value.filter((d) => {
    const plotName = getPlotName(d.plot_id).toLowerCase()
    if (q && !d.serial.toLowerCase().includes(q) && !plotName.includes(q)) return false
    if (statusFilter.value === 'online' && !isOnline(d)) return false
    if (statusFilter.value === 'offline' && isOnline(d)) return false
    return true
  })
})

const hubs = computed(() => filteredDevices.value.filter(d => d.kind === 'gateway'))
const sensors = computed(() => filteredDevices.value.filter(d => d.kind === 'sensor'))
const actuators = computed(() => filteredDevices.value.filter(d => d.kind === 'actuator'))

const counts = computed(() => {
  let online = 0
  for (const d of devices.value) { if (isOnline(d)) online++ }
  return { online, offline: devices.value.length - online, total: devices.value.length }
})

async function load() {
  loading.value = true
  error.value = null
  try {
    if (plotsStore.plots.length === 0) {
      await plotsStore.fetchAll()
    }
    devices.value = await devicesApi.list()

    const acts = devices.value.filter(d => d.kind === 'actuator')
    for (const d of acts) {
      try {
        const { data: pData } = await api.get('/sensor/readings', { 
          params: { device_id: d.id, metric: 'pump_state', limit: 1 } 
        })
        const pState = pData.length > 0 ? pData[0].value : 0
        
        const { data: vData } = await api.get('/sensor/readings', { 
          params: { device_id: d.id, metric: 'valve_state', limit: 1 } 
        })
        const vState = vData.length > 0 ? vData[0].value : 0

        actuatorStates.value[d.id] = {
          pump: pState === 1,
          valve: vState === 1
        }
      } catch {
        actuatorStates.value[d.id] = { pump: false, valve: false }
      }
    }

  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load devices'
  } finally {
    loading.value = false
  }
}

async function toggleMode(d: Device) {
  const currentMode = getControlMode(d)
  const newMode = currentMode === 'auto' ? 'manual' : 'auto'
  const newMeta = { ...d.metadata, control_mode: newMode }
  try {
    await devicesApi.update(d.id, { metadata: newMeta })
    await load()
  } catch {
    alert("Failed to change mode")
  }
}

function openCommand(d: Device) {
  activeDevice.value = d
  actionParams.value = '{}'
  sendResult.value = null
  isOverride.value = getControlMode(d) === 'auto'
  showModal.value = true
}

function openAssign(d: Device) {
  assigningDevice.value = d
  selectedPlotId.value = d.plot_id || ''
  showAssignModal.value = true
}

async function saveAssignment() {
  if (!assigningDevice.value) return
  assigning.value = true
  try {
    await devicesApi.update(assigningDevice.value.id, { 
      plot_id: selectedPlotId.value || null 
    })
    showAssignModal.value = false
    await load()
  } catch (e) {
    alert("Failed to assign plot")
  } finally {
    assigning.value = false
  }
}

async function sendCommand() {
  if (!activeDevice.value) return
  sending.value = true
  sendResult.value = null
  try {
    let params: Record<string, unknown> = {}
    try { params = JSON.parse(actionParams.value) } catch {
      sendResult.value = 'Invalid JSON in params'; sending.value = false; return
    }
    await devicesApi.sendTestCommand(activeDevice.value.id, actionChoice.value, params)
    sendResult.value = `Command sent successfully.`
  } catch (e: any) {
    sendResult.value = e?.response?.data?.detail || 'Failed to send'
  } finally {
    sending.value = false
  }
}

async function toggleEvents(d: Device) {
  if (expandedDeviceId.value === d.id) {
    expandedDeviceId.value = null; return
  }
  expandedDeviceId.value = d.id
  loadingEvents.value = d.id
  try {
    deviceEvents.value[d.id] = await devicesApi.events(d.id, 10)
  } catch {
    deviceEvents.value[d.id] = []
  } finally {
    loadingEvents.value = null
  }
}

onMounted(load)
setInterval(load, 5000)
</script>

<template>
  <div class="max-w-5xl mx-auto space-y-8 pb-20">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="page-title">Farm Hardware</h1>
        <p class="page-subtitle">
          {{ counts.online }} systems online · {{ counts.total }} total registered
        </p>
      </div>
      <button class="btn-ghost text-sm" @click="load" :disabled="loading">
        <Loader2 v-if="loading" :size="14" class="animate-spin" />
        Refresh
      </button>
    </div>

    <div class="flex flex-wrap gap-3">
      <div class="relative flex-1 min-w-[200px]">
        <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input v-model="search" type="text" placeholder="Search by plot name or serial…" class="input pl-9" />
      </div>
      <select v-model="statusFilter" class="input w-40">
        <option value="">All status</option>
        <option value="online">Online Only</option>
        <option value="offline">Offline Only</option>
      </select>
    </div>

    <div v-if="loading && devices.length === 0" class="text-muted flex items-center gap-2">
      <Loader2 :size="16" class="animate-spin" /> Loading hardware…
    </div>
    <div v-else-if="error" class="card text-danger">{{ error }}</div>

    <div v-else class="space-y-10">
      <section v-if="hubs.length > 0" class="space-y-4">
        <div class="flex items-center gap-2 border-b border-border pb-2">
          <Server :size="18" class="text-accent" />
          <h2 class="text-lg font-semibold">Central Controller</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="d in hubs" :key="d.id" class="card border-accent/30 shadow-[0_0_15px_rgba(var(--accent),0.05)]">
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-3">
                <div class="p-2 bg-accent/10 rounded-full text-accent"><Cpu :size="20" /></div>
                <div>
                  <div class="font-semibold">{{ getDeviceName(d) }}</div>
                  <div class="text-xs text-muted font-mono">{{ d.serial }}</div>
                </div>
              </div>
              <div class="flex items-center gap-1.5">
                <component :is="isOnline(d) ? Wifi : WifiOff" :size="14" :class="statusClass(d)" />
                <span :class="['text-xs font-medium', statusClass(d)]">{{ isOnline(d) ? 'Online' : 'Offline' }}</span>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-2 py-3 border-t border-border text-sm">
               <div><span class="text-muted text-xs">Uptime</span><br>{{ fmtUptime(d.uptime_sec) }}</div>
               <div><span class="text-muted text-xs">Signal</span><br>{{ d.rssi_dbm ?? '—' }} dBm</div>
               <div><span class="text-muted text-xs">Last seen</span><br>{{ relativeTime(d.last_seen_at) }}</div>
            </div>
          </div>
        </div>
      </section>

      <section v-if="sensors.length > 0" class="space-y-4">
        <div class="flex items-center gap-2 border-b border-border pb-2">
          <Thermometer :size="18" class="text-water" />
          <h2 class="text-lg font-semibold">Sensors</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="d in sensors" :key="d.id" class="card">
            <div class="flex items-start justify-between mb-4">
              <div>
                <div class="font-semibold flex items-center gap-2">
                  {{ getDeviceName(d) }}
                  <span class="text-[10px] bg-card-hover px-2 py-0.5 rounded text-muted border border-border">Wireless</span>
                  <button v-if="canEdit" @click="openAssign(d)" class="text-muted hover:text-accent transition-colors" title="Assign to Crop Cycle">
                    <PenBox :size="12"/>
                  </button>
                </div>
                <div class="text-xs text-muted font-mono mt-1">{{ d.serial }}</div>
              </div>
              <div class="flex items-center gap-1.5">
                <component :is="isOnline(d) ? Wifi : WifiOff" :size="14" :class="statusClass(d)" />
                <span :class="['text-xs font-medium', statusClass(d)]">{{ isOnline(d) ? 'Online' : 'Offline' }}</span>
              </div>
            </div>
            
            <div class="grid grid-cols-2 gap-3 py-3 border-t border-b border-border">
              <div class="flex items-center gap-2">
                <Battery :size="16" :class="d.battery_v && d.battery_v < 3.5 ? 'text-danger' : 'text-success'" />
                <div>
                  <div class="text-[10px] uppercase text-muted">Battery</div>
                  <div class="text-sm font-medium">{{ d.battery_v ? `${d.battery_v.toFixed(2)}V` : '—' }}</div>
                </div>
              </div>
              <div>
                <div class="text-[10px] uppercase text-muted">Last Report</div>
                <div class="text-sm font-medium">{{ relativeTime(d.last_seen_at) }}</div>
              </div>
            </div>

            <div class="mt-3 flex justify-between items-center">
              <button class="btn-ghost text-xs py-1 px-3" @click="toggleEvents(d)">
                <Activity :size="12" class="mr-1" /> Activity
              </button>
            </div>

            <div v-if="expandedDeviceId === d.id" class="mt-3 pt-3 border-t border-border space-y-2">
              <div v-if="loadingEvents === d.id" class="text-xs text-muted flex items-center gap-1.5">
                <Loader2 :size="11" class="animate-spin" /> Loading…
              </div>
              <div v-else-if="!deviceEvents[d.id] || deviceEvents[d.id].length === 0" class="text-xs text-muted">
                No recent activity.
              </div>
              <div v-else v-for="e in deviceEvents[d.id]" :key="e.id" class="flex items-start gap-2 text-xs">
                <component :is="eventIcon(e)" :size="12" :class="['shrink-0 mt-0.5', eventTone(e)]" />
                <div class="flex-1 min-w-0">
                  <div class="font-mono truncate">
                    <span v-if="e.event_type === 'ack'">ack {{ e.cmd_id }} → {{ e.status }}</span>
                    <span v-else-if="e.event_type === 'error'">{{ e.action }}: {{ e.error }}</span>
                    <span v-else-if="e.event_type === 'manual_override'">Manual override by {{ e.metadata.user }}</span>
                    <span v-else>{{ e.event_type }} {{ e.action || '' }}</span>
                  </div>
                </div>
                <div class="text-[10px] text-muted whitespace-nowrap">{{ relativeTime(e.occurred_at) }}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-if="actuators.length > 0" class="space-y-4">
        <div class="flex items-center gap-2 border-b border-border pb-2">
          <Power :size="18" class="text-warning" />
          <h2 class="text-lg font-semibold">Actuators</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="d in actuators" :key="d.id" class="card border-warning/30">
            <div class="flex items-start justify-between mb-4">
              <div>
                <div class="font-semibold flex items-center gap-2">
                  {{ getDeviceName(d) }}
                  <span class="text-[10px] bg-card-hover px-2 py-0.5 rounded text-muted border border-border">Wired (RS485)</span>
                  <button v-if="canEdit" @click="openAssign(d)" class="text-muted hover:text-accent transition-colors" title="Assign to Crop Cycle">
                    <PenBox :size="12"/>
                  </button>
                </div>
                <div class="text-xs text-muted font-mono mt-1">{{ d.serial }}</div>
              </div>
              <div class="flex items-center gap-1.5">
                <component :is="isOnline(d) ? Wifi : WifiOff" :size="14" :class="statusClass(d)" />
                <span :class="['text-xs font-medium', statusClass(d)]">{{ isOnline(d) ? 'Online' : 'Offline' }}</span>
              </div>
            </div>

            <div class="flex items-center justify-between py-3 border-t border-b border-border">
               <div class="flex items-center gap-4">
                 <div class="flex items-center gap-2">
                   <Droplets :size="16" :class="actuatorStates[d.id]?.pump ? 'text-success animate-pulse' : 'text-water'" />
                   <div>
                     <div class="text-[10px] uppercase text-muted">State</div>
                     <div class="text-sm font-medium" :class="actuatorStates[d.id]?.pump ? 'text-success font-bold' : ''">
                       {{ actuatorStates[d.id]?.pump ? 'Running' : 'Ready' }}
                     </div>
                   </div>
                 </div>
                 
                 <div class="pl-4 border-l border-border flex flex-col items-start">
                   <div class="text-[10px] uppercase text-muted mb-1">Mode</div>
                   <div class="flex items-center gap-2 cursor-pointer" @click="canEdit && toggleMode(d)">
                     <span class="text-[10px] font-bold uppercase transition-colors" :class="getControlMode(d) === 'auto' ? 'text-success' : 'text-muted'">Auto</span>
                     
                     <div class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors"
                          :class="getControlMode(d) === 'auto' ? 'bg-success/30' : 'bg-warning/30'">
                       <span class="inline-block h-3.5 w-3.5 transform rounded-full shadow ring-0 transition duration-200 ease-in-out"
                             :class="getControlMode(d) === 'auto' ? 'translate-x-4.5 bg-success' : 'translate-x-0.5 bg-warning'">
                       </span>
                     </div>

                     <span class="text-[10px] font-bold uppercase transition-colors" :class="getControlMode(d) === 'manual' ? 'text-warning' : 'text-muted'">Manual</span>
                   </div>
                 </div>
               </div>
               
               <button v-if="canEdit" class="btn-primary text-xs py-1.5 px-4 shadow-lg shadow-warning/20" @click="openCommand(d)">
                 <Play :size="12" class="mr-1" /> Control
               </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Test Command Modal -->
    <div v-if="showModal && activeDevice" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="showModal = false">
      <div class="bg-card border border-border rounded-xl w-full max-w-md p-6 space-y-4 shadow-2xl">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">Control {{ getDeviceName(activeDevice) }}</h2>
          <button class="text-muted hover:text-text" @click="showModal = false"><X :size="18" /></button>
        </div>

        <div v-if="isOverride" class="bg-danger/10 border border-danger/30 rounded p-3 flex gap-2 text-danger text-xs">
          <ShieldAlert :size="16" class="shrink-0 mt-0.5" />
          <div>
            <strong>System Override!</strong> This device is in Auto mode. Sending a manual command will temporarily override the automated system and will be logged in the audit trail.
          </div>
        </div>
        
        <div class="text-xs text-muted font-mono bg-card-hover p-2 rounded">
          {{ activeDevice.serial }}
        </div>

        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">Action</label>
          <select v-model="actionChoice" class="input w-full">
            <template v-if="activeDevice.kind === 'actuator'">
              <!-- Disable options based on current state -->
              <option value="irrigation.start" :disabled="actuatorStates[activeDevice.id]?.pump">
                Turn Pump ON {{ actuatorStates[activeDevice.id]?.pump ? '(Already Running)' : '' }}
              </option>
              <option value="irrigation.stop" :disabled="!actuatorStates[activeDevice.id]?.pump">
                Turn Pump OFF {{ !actuatorStates[activeDevice.id]?.pump ? '(Already Off)' : '' }}
              </option>
              <option value="valve.open" :disabled="actuatorStates[activeDevice.id]?.valve">
                Open Valve {{ actuatorStates[activeDevice.id]?.valve ? '(Already Open)' : '' }}
              </option>
              <option value="valve.close" :disabled="!actuatorStates[activeDevice.id]?.valve">
                Close Valve {{ !actuatorStates[activeDevice.id]?.valve ? '(Already Closed)' : '' }}
              </option>
            </template>
            <option value="reboot">Reboot Device</option>
          </select>
        </div>

        <div v-if="actionChoice === 'irrigation.start' || actionChoice === 'valve.open'">
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">Params (JSON)</label>
          <textarea v-model="actionParams" rows="2" class="input w-full font-mono text-xs" placeholder='{"duration_sec": 60}' />
          <p class="text-[10px] text-muted mt-1">Provide a duration to auto-shutoff. Empty means run forever.</p>
        </div>

        <div v-if="sendResult" class="text-xs bg-card-hover rounded p-3 font-medium">
          {{ sendResult }}
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button class="btn-ghost text-sm" @click="showModal = false">Cancel</button>
          <button class="btn-primary text-sm shadow-lg shadow-accent/20" :disabled="sending" @click="sendCommand">
            <Loader2 v-if="sending" :size="14" class="animate-spin" />
            <Play v-else :size="14" />
            {{ isOverride ? 'Confirm Override' : 'Send Command' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Assign Plot Modal -->
    <div v-if="showAssignModal && assigningDevice" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="showAssignModal = false">
      <div class="bg-card border border-border rounded-xl w-full max-w-sm p-6 space-y-4 shadow-2xl">
        <h2 class="text-lg font-semibold">Assign Device</h2>
        <div class="text-xs text-muted font-mono bg-card-hover p-2 rounded">{{ assigningDevice.serial }}</div>
        
        <div>
          <label class="block text-xs uppercase text-muted mb-1">Select Crop Cycle (Plot)</label>
          <select v-model="selectedPlotId" class="input w-full">
            <option value="">-- Unassigned --</option>
            <option v-for="plot in plotsStore.plots" :key="plot.id" :value="plot.id">
              {{ plot.name }} ({{ plot.crop }})
            </option>
          </select>
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button class="btn-ghost text-sm" @click="showAssignModal = false">Cancel</button>
          <button class="btn-primary text-sm" :disabled="assigning" @click="saveAssignment">
            <Loader2 v-if="assigning" :size="14" class="animate-spin" /> Save
          </button>
        </div>
      </div>
    </div>
  </div>
</template>