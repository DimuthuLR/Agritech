<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, Leaf, Activity, Wallet,
  AlertTriangle, CheckCircle, XCircle, Clock,
  ClipboardList, Plus, Check, X as XIcon,
  Power, Play, Loader2, ShieldAlert, Droplets
} from 'lucide-vue-next'
import { usePlotsStore } from '../stores/plots'
import { tasksApi } from '../api/tasks'
import { diagnosesApi, type Diagnosis } from '../api/diagnoses'
import { financeApi, type CostSummary } from '../api/finance'
import { fieldEventsApi, type FieldEvent } from '../api/field_events'
import { sensorsApi } from '../api/sensors'
import { devicesApi } from '../api/devices'
import { api } from '../api/client'
import type { Device } from '../types/device'
import { useAuthStore } from '../stores/auth'
import { SOIL_TYPE_LABELS, type Plot } from '../types/plot'
import type { Task } from '../types/task'
import { useSensorStream } from '../composables/useSensorStream'
import { defineAsyncComponent } from 'vue'
const SensorChart = defineAsyncComponent(
  () => import('../components/charts/SensorChart.vue')
)
import RecordOverrideModal from '../components/field_events/RecordOverrideModal.vue'

const route = useRoute()
const router = useRouter()
const store = usePlotsStore()
const authStore = useAuthStore()

const plotId = computed(() => route.params.id as string)
const plot = ref<Plot | null>(null)
const tasks = ref<Task[]>([])
const diagnoses = ref<Diagnosis[]>([])
const costs = ref<CostSummary | null>(null)
const fieldEvents = ref<FieldEvent[]>([])
const showOverrideModal = ref(false)
const loading = ref(true)

// --- Chart Time Filter ---
const timeRange = ref<'24h' | '7d' | '30d'>('24h')

// --- Live sensor stream ---
const sensors = useSensorStream(plotId.value)

watch(plotId, (newId) => {
  if (newId) {
    sensors.disconnect()
    sensors.connect()
    loadChartData()
  }
})

watch(timeRange, () => {
  loadChartData()
})

const soilData = computed(() => sensors.series.value.soil_moisture ?? [])
const tempData = computed(() => sensors.series.value.temperature ?? [])
const humidData = computed(() => sensors.series.value.humidity ?? [])

// --- Actuators State ---
const actuators = ref<Device[]>([])
const actuatorStates = ref<Record<string, { pump: boolean, valve: boolean }>>({})
const showCommandModal = ref(false)
const activeActuator = ref<Device | null>(null)
const actionChoice = ref('irrigation.start')
const actionParams = ref<string>('{}')
const sending = ref(false)
const sendResult = ref<string | null>(null)
const isOverride = ref(false)
const showConfirmOverride = ref(false)

const canEdit = computed(() => {
  const role = authStore.user?.tenant_role
  if (!role) return false
  const normalizedRole = role.toLowerCase().replace(/[\s_]/g, '')
  return normalizedRole === 'tenantadmin' || normalizedRole === 'operator'
})

const soilLabel = computed(() => plot.value ? SOIL_TYPE_LABELS[plot.value.soil_type] : '')
const pendingTasks = computed(() => tasks.value.filter((t) => t.status === 'pending_approval'))
const recentTasks = computed(() => tasks.value.slice(0, 5))
const recentDiagnoses = computed(() => diagnoses.value.filter((d) => d.status === 'complete').slice(0, 3))

// --- Cost category display ---
const CATEGORY_LABELS: Record<string, string> = {
  water: 'Water', fertilizer: 'Fertilizer', chemical: 'Chemical',
  labor: 'Labor', energy: 'Energy', fuel: 'Fuel', seed: 'Seed',
  equipment: 'Equipment', other: 'Other',
}

const costRows = computed(() => {
  if (!costs.value) return []
  return Object.entries(costs.value.breakdown)
    .filter(([_, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([k, v]) => ({ key: k, label: CATEGORY_LABELS[k] || k, value: v }))
})

function statusIcon(status: string) {
  switch (status) {
    case 'done': return CheckCircle
    case 'pending_approval': return Clock
    case 'rejected': case 'failed': return XCircle
    case 'dispatched': case 'acked': case 'approved': return Activity
    default: return AlertTriangle
  }
}
function statusColor(status: string) {
  switch (status) {
    case 'done': return 'text-success'
    case 'pending_approval': return 'text-warning'
    case 'rejected': case 'failed': return 'text-danger'
    default: return 'text-water'
  }
}
function actionLabel(tool: string | null): string {
  if (!tool) return 'Action'
  const labels: Record<string, string> = {
    control_irrigation: 'Irrigation', schedule_fertigation: 'Fertigation',
    spray_chemical: 'Chemical spray', other: 'Other action',
  }
  return labels[tool] || tool
}

// --- Data Loading ---
function loadChartData() {
  // Clear existing data when time range changes so it doesn't overlap
  sensors.series.value = {}
  
  const bucket = timeRange.value === '24h' ? '1h' : '6h'
  
  sensorsApi.summary(plotId.value, bucket as any, timeRange.value)
    .then((buckets) => {
      const byMetric: Record<string, { time: string; value: number }[]> = {}
      for (const b of buckets) {
        ;(byMetric[b.metric] ??= []).push({
          time: b.bucket,
          value: b.avg_value,
        })
      }
      for (const [metric, points] of Object.entries(byMetric)) {
        sensors.seed(metric, points)
      }
    })
    .catch(() => {})
}

function getControlMode(d: Device): 'auto' | 'manual' {
  return (d.metadata?.control_mode as string) || 'manual'
}

async function toggleMode(d: Device) {
  const newMode = getControlMode(d) === 'auto' ? 'manual' : 'auto'
  const newMeta = { ...d.metadata, control_mode: newMode }
  try {
    await devicesApi.update(d.id, { metadata: newMeta })
    await loadActuators()
  } catch {
    alert("Failed to change mode")
  }
}

async function loadActuators() {
  try {
    const allDevices = await devicesApi.list()
    const plotActs = allDevices.filter(d => String(d.plot_id) === String(plotId.value) && d.kind === 'actuator')
    actuators.value = plotActs

    for (const d of plotActs) {
      try {
        const { data: pData } = await api.get('/sensor/readings', { 
          params: { device_id: d.id, metric: 'pump_state', limit: 1 } 
        })
        const pState = pData.length > 0 ? pData[0].value : 0
        
        const { data: vData } = await api.get('/sensor/readings', { 
          params: { device_id: d.id, metric: 'valve_state', limit: 1 } 
        })
        const vState = vData.length > 0 ? vData[0].value : 0

        actuatorStates.value[d.id] = { pump: pState === 1, valve: vState === 1 }
      } catch {
        actuatorStates.value[d.id] = { pump: false, valve: false }
      }
    }
  } catch (e) {}
}

async function loadAll() {
  loading.value = true
  try {
    const cached = store.plots.find((p) => p.id === plotId.value)
    plot.value = cached ?? (await store.fetchOne(plotId.value))

    const [t, d, c, fe] = await Promise.allSettled([
      tasksApi.list(plotId.value),
      diagnosesApi.list(plotId.value),
      financeApi.plotSummary(plotId.value),
      fieldEventsApi.list(plotId.value, 90),
    ])
    if (t.status === 'fulfilled') tasks.value = t.value
    if (d.status === 'fulfilled') diagnoses.value = d.value
    if (c.status === 'fulfilled') costs.value = c.value
    if (fe.status === 'fulfilled') fieldEvents.value = fe.value

    await loadActuators()
  } finally {
    loading.value = false
  }
}

function openCommand(d: Device) {
  activeActuator.value = d
  const state = actuatorStates.value[d.id]
  actionChoice.value = state?.pump ? 'irrigation.stop' : 'irrigation.start'
  actionParams.value = '{}'
  sendResult.value = null
  isOverride.value = getControlMode(d) === 'auto'
  showCommandModal.value = true
}

async function sendCommand() {
  if (!activeActuator.value) return
  
  if (isOverride.value) {
    showConfirmOverride.value = true
    return
  }
  await executeCommand()
}

async function executeCommand() {
  if (!activeActuator.value) return
  sending.value = true
  sendResult.value = null
  try {
    let params: Record<string, unknown> = {}
    try { params = JSON.parse(actionParams.value) } catch {
      sendResult.value = 'Invalid JSON'; sending.value = false; return
    }
    await devicesApi.sendTestCommand(activeActuator.value.id, actionChoice.value, params)
    sendResult.value = 'Command sent successfully.'
    showConfirmOverride.value = false
    setTimeout(() => { loadActuators() }, 2000)
  } catch (e: any) {
    sendResult.value = e?.response?.data?.detail || 'Failed to send'
  } finally {
    sending.value = false
  }
}

function onOverrideCreated(event: FieldEvent) {
  fieldEvents.value = [event, ...fieldEvents.value]
}

onMounted(async () => {
  loadAll()
  loadChartData()
  if (plotId.value) sensors.connect()
})
</script>

<template>
  <div class="max-w-5xl mx-auto space-y-6 pb-20">

    <!-- Back + Header -->
    <div>
      <button
        class="text-muted hover:text-text text-sm inline-flex items-center gap-1 mb-3 transition-colors"
        @click="router.push({ name: 'plots' })"
      >
        <ArrowLeft :size="14" :stroke-width="1.75" />
        Back to plots
      </button>

      <div v-if="loading" class="text-muted">Loading…</div>

      <div v-else-if="!plot" class="card text-danger">
        Plot not found.
      </div>

      <div v-else class="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 class="text-2xl font-semibold">{{ plot.name }}</h1>
          <p class="text-sm text-muted mt-1">
            {{ soilLabel }}
            <span v-if="plot.crop"> · {{ plot.crop }}</span>
            <span v-if="plot.stage"> · {{ plot.stage }}</span>
            <span> · {{ plot.area_ha }} ha</span>
          </p>
        </div>

        <div v-if="pendingTasks.length" class="pill-warning">
          <Clock :size="12" :stroke-width="2" />
          {{ pendingTasks.length }} pending task{{ pendingTasks.length === 1 ? '' : 's' }}
        </div>
      </div>
    </div>

    <!-- Summary tiles -->
    <div v-if="!loading && plot" class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Leaf :size="14" :stroke-width="1.75" /> Crop
        </div>
        <div class="text-2xl font-semibold mt-2 capitalize">{{ plot.crop || '—' }}</div>
        <div class="text-xs text-muted mt-1">{{ plot.stage || 'no stage set' }}</div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Activity :size="14" :stroke-width="1.75" /> Recent tasks
        </div>
        <div class="text-2xl font-semibold mt-2">{{ tasks.length }}</div>
        <div class="text-xs text-muted mt-1">{{ pendingTasks.length }} awaiting approval</div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Wallet :size="14" :stroke-width="1.75" /> Total cost
        </div>
        <div class="text-2xl font-semibold mt-2">LKR {{ costs?.total_lkr?.toFixed(0) || '0' }}</div>
        <div class="text-xs text-muted mt-1">all time</div>
      </div>
    </div>

    <!-- Live sensor charts -->
    <section v-if="!loading && plot">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <h2 class="text-lg font-semibold">Live sensors</h2>
          
          <!-- Time Range Filter -->
          <div class="flex bg-card-hover rounded-md p-1 border border-border/50">
            <button 
              @click="timeRange = '24h'"
              :class="['text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded transition-colors', timeRange === '24h' ? 'bg-card text-text shadow-sm' : 'text-muted hover:text-text']"
            >Daily</button>
            <button 
              @click="timeRange = '7d'"
              :class="['text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded transition-colors', timeRange === '7d' ? 'bg-card text-text shadow-sm' : 'text-muted hover:text-text']"
            >Weekly</button>
            <button 
              @click="timeRange = '30d'"
              :class="['text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded transition-colors', timeRange === '30d' ? 'bg-card text-text shadow-sm' : 'text-muted hover:text-text']"
            >Monthly</button>
          </div>
        </div>

        <span
          :class="[
            'pill text-xs',
            sensors.connected.value ? 'bg-success/10 text-success' : 'bg-muted/10 text-muted',
          ]"
        >
          <span :class="['w-1.5 h-1.5 rounded-full', sensors.connected.value ? 'bg-success animate-pulse' : 'bg-muted']" />
          {{ sensors.connected.value ? 'Live' : 'Connecting…' }}
        </span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <SensorChart title="Soil moisture" unit="" :data="soilData" color="#38BDF8" :min-value="0" :max-value="1" />
        <SensorChart title="Temperature" unit="°C" :data="tempData" color="#F59E0B" />
        <SensorChart title="Humidity" unit="" :data="humidData" color="#34D399" :min-value="0" :max-value="1" />
      </div>
    </section>

    <!-- Actuators Section -->
    <section v-if="!loading && actuators.length > 0" class="space-y-4">
      <h2 class="text-lg font-semibold flex items-center gap-2">
        <Power :size="18" class="text-warning" /> Actuators
      </h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="d in actuators" :key="d.id" class="card border-warning/20">
          
          <div class="flex items-center justify-between mb-3">
            <div class="font-semibold text-sm">{{ d.serial }}</div>
            <div class="text-xs text-muted font-mono">RS485</div>
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

    <!-- Recent Tasks -->
    <section v-if="!loading && plot">
      <h2 class="text-lg font-semibold mb-3">Recent tasks</h2>
      <div v-if="recentTasks.length === 0" class="card text-sm text-muted">
        No tasks yet for this plot.
      </div>
      <div v-else class="card p-0 divide-y divide-border">
        <div v-for="t in recentTasks" :key="t.id" class="p-4 flex items-start gap-3">
          <component :is="statusIcon(t.status)" :size="18" :stroke-width="1.75" :class="['shrink-0 mt-0.5', statusColor(t.status)]" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-medium text-sm">{{ t.tool }}</span>
              <span class="pill bg-card-hover text-muted text-xs">{{ t.status }}</span>
            </div>
            <p class="text-xs text-muted mt-1 line-clamp-2">{{ t.reason }}</p>
            <p class="text-xs text-muted mt-1">{{ new Date(t.created_at).toLocaleString() }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Recent Diagnoses -->
    <section v-if="!loading && plot">
      <h2 class="text-lg font-semibold mb-3">Recent diagnoses</h2>
      <div v-if="recentDiagnoses.length === 0" class="card text-sm text-muted">
        No diagnoses yet. Upload a leaf photo to start.
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="d in recentDiagnoses" :key="d.id" class="card">
          <div class="flex items-start justify-between gap-2 mb-2">
            <div>
              <div class="font-medium text-sm">{{ d.disease || 'Unknown' }}</div>
              <div class="text-xs text-muted">{{ d.severity || '—' }} severity</div>
            </div>
            <div v-if="d.confidence" class="text-xs text-muted">{{ Math.round(d.confidence * 100) }}%</div>
          </div>
          <div class="text-xs text-muted">
            Cost:
            <span class="text-text font-medium">LKR {{ (d.calculated_cost_lkr || d.estimated_cost_lkr || 0).toFixed(0) }}</span>
            <span v-if="d.calculated_cost_lkr" class="text-success ml-1">(calculated)</span>
            <span v-else class="ml-1">(estimate)</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Cost breakdown -->
    <section v-if="!loading && plot && costRows.length > 0">
      <h2 class="text-lg font-semibold mb-3">Cost breakdown</h2>
      <div class="card space-y-3">
        <div v-for="row in costRows" :key="row.key" class="flex items-center gap-3">
          <div class="w-24 text-sm text-muted">{{ row.label }}</div>
          <div class="flex-1 h-2 bg-card-hover rounded-full overflow-hidden">
            <div class="h-full bg-water rounded-full transition-all" :style="{ width: `${(row.value / costs!.total_lkr) * 100}%` }" />
          </div>
          <div class="w-24 text-right text-sm tabular-nums">LKR {{ row.value.toFixed(0) }}</div>
        </div>
      </div>
    </section>

    <!-- Overrides / self-recorded actions -->
    <section v-if="!loading && plot">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Our own actions</h2>
        <button class="btn-ghost text-xs py-1.5 px-3" @click="showOverrideModal = true">
          <Plus :size="14" :stroke-width="2" /> Record action
        </button>
      </div>

      <div v-if="fieldEvents.length === 0" class="card text-sm text-muted text-center py-6">
        <ClipboardList :size="20" :stroke-width="1.5" class="mx-auto mb-2" />
        <p>When you act against the platform's advice, record it here. The AI learns from your experience.</p>
      </div>

      <div v-else class="card p-0 divide-y divide-border">
        <div v-for="e in fieldEvents.slice(0, 5)" :key="e.id" class="p-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">{{ actionLabel(e.action_taken) }}</span>
                <span v-if="e.outcome === 'worked'" class="pill-success text-xs"><Check :size="11" :stroke-width="2" /> Justified</span>
                <span v-else-if="e.outcome === 'failed'" class="pill-danger text-xs"><XIcon :size="11" :stroke-width="2" /> Not justified</span>
                <span v-else class="pill-muted text-xs"><Clock :size="11" :stroke-width="2" /> Awaiting verification</span>
              </div>
              <p class="text-xs text-muted mt-1.5 line-clamp-2">{{ e.reason }}</p>
            </div>
            <span class="text-xs text-muted shrink-0">{{ new Date(e.occurred_at).toLocaleDateString() }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Record Override Modal -->
    <RecordOverrideModal :open="showOverrideModal" :plot-id="plotId" @close="showOverrideModal = false" @created="onOverrideCreated" />

    <!-- Control Actuator Modal -->
    <div v-if="showCommandModal && activeActuator" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="showCommandModal = false">
      <div class="bg-card border border-border rounded-xl w-full max-w-md p-6 space-y-4 shadow-2xl">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">Control {{ activeActuator.serial }}</h2>
          <button class="text-muted hover:text-text" @click="showCommandModal = false"><XIcon :size="18" /></button>
        </div>
        
        <div class="text-xs text-muted font-mono bg-card-hover p-2 rounded">{{ activeActuator.serial }}</div>

        <div>
          <label class="block text-xs uppercase tracking-wide text-muted mb-1">Action</label>
          <select v-model="actionChoice" class="input w-full">
            <option value="irrigation.start" :disabled="actuatorStates[activeActuator.id]?.pump">Turn Pump ON</option>
            <option value="irrigation.stop" :disabled="!actuatorStates[activeActuator.id]?.pump">Turn Pump OFF</option>
            <option value="valve.open" :disabled="actuatorStates[activeActuator.id]?.valve">Open Valve</option>
            <option value="valve.close" :disabled="!actuatorStates[activeActuator.id]?.valve">Close Valve</option>
          </select>
        </div>

        <div v-if="sendResult" class="text-xs bg-card-hover rounded p-3 font-medium">{{ sendResult }}</div>

        <div class="flex justify-end gap-2 pt-2">
          <button class="btn-ghost text-sm" @click="showCommandModal = false">Cancel</button>
          <button class="btn-primary text-sm" :disabled="sending" @click="sendCommand">
            <Loader2 v-if="sending" :size="14" class="animate-spin" /> Send
          </button>
        </div>
      </div>
    </div>

    <!-- Override Confirm Modal -->
    <div v-if="showConfirmOverride" class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 backdrop-blur-sm" @click.self="showConfirmOverride = false">
      <div class="bg-card border border-border rounded-xl w-full max-w-sm p-6 space-y-4 shadow-2xl text-left">
        <div class="flex items-center gap-3 text-danger mb-2">
          <div class="p-2 bg-danger/10 rounded-full"><ShieldAlert :size="20" /></div>
          <h2 class="text-lg font-bold">System Override</h2>
        </div>
        <p class="text-sm text-text/80">This device is in <strong>Auto mode</strong>. Sending a manual command will temporarily override the AI's automation.</p>
        <p class="text-xs text-muted">This action will be permanently recorded in the audit log.</p>
        <div class="flex justify-end gap-2 pt-2">
          <button class="btn-ghost text-sm" @click="showConfirmOverride = false">Cancel</button>
          <button class="btn-primary text-sm bg-danger hover:bg-danger/90 text-white shadow-lg shadow-danger/20" @click="executeCommand">
            Confirm Override
          </button>
        </div>
      </div>
    </div>
  </div>
</template>