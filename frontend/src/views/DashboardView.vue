<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { devicesApi } from '../api/devices'
import type { Device } from '../types/device'
import {
  Sprout, Droplets, Activity, Wallet, CheckSquare,
  Leaf, AlertTriangle, CheckCircle, Clock,
  Cloud, CloudRain, Sun, Wind, Thermometer,
  ArrowRight, Loader2, Battery, Power, LayoutGrid
} from 'lucide-vue-next'

// ─── Types ───────────────────────────────────────────────────────────────
interface Plot {
  id: string
  name: string
  crop: string | null
  stage: string | null
  area_ha: number
  soil_type: string
  latitude: number | null
  longitude: number | null
  farm_id: string
}

interface Task {
  id: string
  plot_id: string
  tool: string
  status: string
  reason: string | null
  created_at: string
}

interface Diagnosis {
  id: string
  plot_id: string
  disease: string | null
  severity: string | null
  confidence: number | null
  status: string
  created_at: string
}

interface FieldEvent {
  id: string
  plot_id: string
  action_taken: string | null
  event_type: string
  outcome: string | null
  reason: string | null
  occurred_at: string
}

interface FinanceOverview {
  window_days: number
  total_lkr: number
  entry_count: number
  breakdown: Record<string, number>
  by_plot: { plot_id: string; name: string; total_lkr: number }[]
  trend: { day: string; total_lkr: number }[]
}

interface SensorReading {
  time: string
  device_id: string
  metric: string
  value: number
}

interface PlotStatus {
  plot: Plot
  soilMoisture: number | null
  temperature: number | null
  humidity: number | null
  batteryV: number | null
  activeActuators: string[]
  lastWateredAt: string | null
  latestDiagnosis: Diagnosis | null
}

// ─── State ───────────────────────────────────────────────────────────────
const auth = useAuthStore()
const router = useRouter()

const plots = ref<Plot[]>([])
const tasks = ref<Task[]>([])
const diagnoses = ref<Diagnosis[]>([])
const fieldEvents = ref<FieldEvent[]>([])
const finance = ref<FinanceOverview | null>(null)
const plotStatuses = ref<PlotStatus[]>([])
const weather = ref<any>(null)
const loading = ref(true)

// ─── Derived ─────────────────────────────────────────────────────────────
const pendingTasks = computed(() =>
  tasks.value.filter((t) => t.status === 'pending_approval'),
)

const recentTasks = computed(() =>
  [...tasks.value]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 4),
)

const recentDiagnoses = computed(() =>
  diagnoses.value
    .filter((d) => d.status === 'complete')
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 3),
)

const recentActivity = computed(() => {
  type Row = { at: string; icon: any; label: string; sub: string; plot: string | null }
  const rows: Row[] = []

  for (const t of recentTasks.value) {
    rows.push({
      at: t.created_at,
      icon: CheckSquare,
      label: `Task · ${humanTool(t.tool)}`,
      sub: t.status.replace(/_/g, ' '),
      plot: t.plot_id,
    })
  }
  for (const d of recentDiagnoses.value) {
    rows.push({
      at: d.created_at,
      icon: Leaf,
      label: `Diagnosis · ${d.disease || 'unknown'}`,
      sub: d.severity ? `${d.severity} severity` : '',
      plot: d.plot_id,
    })
  }
  for (const e of fieldEvents.value.slice(0, 3)) {
    rows.push({
      at: e.occurred_at,
      icon: Activity,
      label: `Field action · ${e.action_taken || e.event_type}`,
      sub: e.outcome || 'awaiting verification',
      plot: e.plot_id,
    })
  }

  return rows
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, 6)
})

const totalArea = computed(() =>
  plots.value.reduce((s, p) => s + (p.area_ha || 0), 0),
)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
})

const firstName = computed(() =>
  (auth.user?.full_name || auth.user?.email || '').split(/[@\s]/)[0] || 'farmer',
)

// ─── Helpers ─────────────────────────────────────────────────────────────
function humanTool(t: string): string {
  const map: Record<string, string> = {
    control_irrigation: 'Irrigation',
    schedule_fertigation: 'Fertigation',
    spray_chemical: 'Chemical spray',
    other: 'Other',
  }
  return map[t] || t
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
  if (d === 1) return 'yesterday'
  if (d < 30) return `${d}d ago`
  return `${Math.floor(d / 30)}mo ago`
}

function fmtCurrency(n: number): string {
  return `LKR ${Math.round(n).toLocaleString()}`
}

function healthFor(status: PlotStatus): { label: string; tone: string; icon: any } {
  const d = status.latestDiagnosis
  if (!d) return { label: 'No recent issues', tone: 'text-muted', icon: CheckCircle }
  if (d.severity === 'high') return { label: `${d.disease} · high`, tone: 'text-danger', icon: AlertTriangle }
  if (d.severity === 'moderate') return { label: `${d.disease} · moderate`, tone: 'text-warning', icon: AlertTriangle }
  return { label: `${d.disease} · ${d.severity || 'low'}`, tone: 'text-success', icon: CheckCircle }
}

function moistureTone(v: number | null): string {
  if (v === null) return 'text-muted'
  if (v < 0.30) return 'text-danger'
  if (v < 0.50) return 'text-warning'
  return 'text-success'
}

function tempTone(v: number | null): string {
  if (v === null) return 'text-muted'
  if (v > 35) return 'text-danger'
  if (v > 30) return 'text-warning'
  return 'text-text'
}

function weatherInfo(code: number): { icon: any; label: string } {
  if (code === 0) return { icon: Sun, label: 'Clear' }
  if (code <= 2) return { icon: Sun, label: 'Partly cloudy' }
  if (code <= 48) return { icon: Cloud, label: 'Cloudy' }
  if (code <= 67) return { icon: CloudRain, label: 'Rain' }
  if (code <= 82) return { icon: CloudRain, label: 'Showers' }
  return { icon: CloudRain, label: 'Storm' }
}

// ─── Data loading ────────────────────────────────────────────────────────
async function loadPlotStatus(p: Plot, devices: Device[]): Promise<PlotStatus> {
  let soilMoisture = null
  let temperature = null
  let humidity = null
  const activeActuators: string[] = []

  try {
    const { data } = await api.get<SensorReading[]>('/sensor/readings', {
      params: { plot_id: p.id, limit: 20 }
    })
    const seenMetrics = new Set()
    
    for (const r of data) {
      if (seenMetrics.has(r.metric)) continue
      seenMetrics.add(r.metric)

      if (r.metric === 'soil_moisture') soilMoisture = r.value
      if (r.metric === 'temperature') temperature = r.value
      if (r.metric === 'humidity') humidity = r.value
      if (r.metric.endsWith('_state') && r.value === 1) {
        activeActuators.push(r.metric.replace('_state', ''))
      }
    }
  } catch (e) {}

  let batteryV = null
  const plotSensors = devices.filter(d => d.plot_id === p.id && d.kind === 'sensor')
  for (const s of plotSensors) {
    if (s.battery_v !== null) {
      if (batteryV === null || s.battery_v < batteryV) {
        batteryV = s.battery_v
      }
    }
  }

  const lastIrrigation = tasks.value
    .filter(t => t.plot_id === p.id && t.tool === 'control_irrigation' && (t.status === 'done' || t.status === 'acked'))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]

  const latestDiag = diagnoses.value
    .filter(d => d.plot_id === p.id && d.status === 'complete')
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null

  return {
    plot: p,
    soilMoisture,
    temperature,
    humidity,
    batteryV,
    activeActuators,
    lastWateredAt: lastIrrigation?.created_at || null,
    latestDiagnosis: latestDiag
  }
}

async function loadWeather(lat: number, lng: number): Promise<void> {
  try {
    const url = 'https://api.open-meteo.com/v1/forecast'
    const { data } = await api.get(url, {
      baseURL: '',
      params: {
        latitude: lat,
        longitude: lng,
        current: 'temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m',
        timezone: 'auto',
      },
    })
    weather.value = data.current
  } catch {
    weather.value = null
  }
}

async function load() {
  loading.value = true
  try {
    const [plotsRes, devicesRes, tasksRes, diagRes, eventsRes, finRes] =
      await Promise.allSettled([
        api.get<Plot[]>('/plots'),
        devicesApi.list(),
        api.get<Task[]>('/tasks'),
        api.get<Diagnosis[]>('/diagnosis', { params: { limit: 20 } }),
        api.get<FieldEvent[]>('/field-events', { params: { days: 30, limit: 20 } }),
        api.get<FinanceOverview>('/finance/overview', { params: { days: 30 } }),
      ])

    plots.value = plotsRes.status === 'fulfilled' ? plotsRes.value.data : []
    const devices = devicesRes.status === 'fulfilled' ? devicesRes.value : []
    tasks.value = tasksRes.status === 'fulfilled' ? tasksRes.value.data : []
    diagnoses.value = diagRes.status === 'fulfilled' ? diagRes.value.data : []
    fieldEvents.value = eventsRes.status === 'fulfilled' ? eventsRes.value.data : []
    finance.value = finRes.status === 'fulfilled' ? finRes.value.data : null

    const statusPromises = plots.value.map(p => loadPlotStatus(p, devices))
    plotStatuses.value = await Promise.all(statusPromises)

    const withCoords = plots.value.find((p) => p.latitude && p.longitude)
    const lat = withCoords?.latitude ?? 6.9271
    const lng = withCoords?.longitude ?? 79.8612
    await loadWeather(lat, lng)

  } finally {
    loading.value = false
  }
}

onMounted(load)

const weatherVisual = computed(() => {
  if (!weather.value) return { icon: Sun, label: '—' }
  return weatherInfo(weather.value.weather_code)
})
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- ── Header ────────────────────────────────────────────── -->
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl font-semibold">
          {{ greeting }}, {{ firstName }}
        </h1>
        <p class="text-sm text-muted mt-1">
          {{ new Date().toLocaleDateString(undefined, {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
          }) }}
        </p>
      </div>

      <!-- Weather widget -->
      <div v-if="weather" class="card flex items-center gap-4 min-w-[220px] bg-gradient-to-br from-card to-card-hover border-water/20 shadow-sm">
        <component :is="weatherVisual.icon" :size="32" :stroke-width="1.5" class="text-water shrink-0" />
        <div class="flex-1">
          <div class="text-2xl font-semibold leading-none">
            {{ Math.round(weather.temperature_2m) }}°C
          </div>
          <div class="text-xs text-muted mt-1 flex items-center gap-3 flex-wrap">
            <span>{{ weatherVisual.label }}</span>
            <span class="flex items-center gap-1">
              <Wind :size="11" /> {{ Math.round(weather.wind_speed_10m) }} km/h
            </span>
            <span class="flex items-center gap-1">
              <Thermometer :size="11" /> {{ weather.relative_humidity_2m }}%
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Top stat row (Enhanced with background icons) ──────────────────────────────────────── -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="card relative overflow-hidden group">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Sprout :size="14" :stroke-width="1.75" /> Plots
        </div>
        <div class="text-3xl font-bold mt-2">{{ plots.length }}</div>
        <div class="text-xs text-muted mt-1">{{ totalArea.toFixed(2) }} ha total</div>
        <LayoutGrid :size="64" class="absolute -right-2 -bottom-2 text-text opacity-[0.03] group-hover:opacity-[0.06] transition-opacity" />
      </div>

      <div class="card relative overflow-hidden group">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <CheckSquare :size="14" :stroke-width="1.75" /> Pending
        </div>
        <div class="text-3xl font-bold mt-2" :class="pendingTasks.length > 0 ? 'text-warning' : ''">{{ pendingTasks.length }}</div>
        <div class="text-xs text-muted mt-1">{{ pendingTasks.length ? 'needs approval' : 'all clear' }}</div>
        <CheckSquare :size="64" class="absolute -right-2 -bottom-2 text-text opacity-[0.03] group-hover:opacity-[0.06] transition-opacity" />
      </div>

      <div class="card relative overflow-hidden group">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Wallet :size="14" :stroke-width="1.75" /> Spend · 30d
        </div>
        <div class="text-3xl font-bold mt-2">{{ finance ? fmtCurrency(finance.total_lkr) : '—' }}</div>
        <div class="text-xs text-muted mt-1">{{ finance?.entry_count ?? 0 }} ledger entries</div>
        <Wallet :size="64" class="absolute -right-2 -bottom-2 text-text opacity-[0.03] group-hover:opacity-[0.06] transition-opacity" />
      </div>

      <div class="card relative overflow-hidden group">
        <div class="flex items-center gap-2 text-muted text-xs tracking-wide uppercase">
          <Leaf :size="14" :stroke-width="1.75" /> Diagnoses
        </div>
        <div class="text-3xl font-bold mt-2">{{ diagnoses.length }}</div>
        <div class="text-xs text-muted mt-1">{{ recentDiagnoses.length }} recent results</div>
        <Leaf :size="64" class="absolute -right-2 -bottom-2 text-text opacity-[0.03] group-hover:opacity-[0.06] transition-opacity" />
      </div>
    </div>

    <!-- ── Loading ───────────────────────────────────────────── -->
    <div v-if="loading" class="text-muted flex items-center justify-center py-12">
      <Loader2 :size="24" class="animate-spin text-accent" />
    </div>

    <!-- ── Plots grid ───────────────────────────────────────── -->
    <section v-if="!loading && plotStatuses.length">
      <div class="flex items-center justify-between mb-4 mt-8">
        <h2 class="text-xl font-semibold tracking-tight">Your plots</h2>
        <button
          class="text-xs font-medium text-muted hover:text-accent transition-colors flex items-center gap-1 uppercase tracking-wider"
          @click="router.push({ name: 'plots' })"
        >
          View all <ArrowRight :size="12" />
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div
          v-for="s in plotStatuses"
          :key="s.plot.id"
          class="card group cursor-pointer hover:border-accent/40 hover:shadow-lg hover:shadow-accent/5 transition-all duration-300 flex flex-col p-0 overflow-hidden"
          @click="router.push({ name: 'plot-detail', params: { id: s.plot.id } })"
        >
          <!-- Card Header -->
          <div class="p-5 pb-4 flex items-start justify-between gap-3 border-b border-border/50">
            <div class="min-w-0">
              <div class="text-lg font-bold truncate tracking-tight group-hover:text-accent transition-colors">{{ s.plot.name }}</div>
              <div class="text-xs text-muted mt-1 flex items-center gap-1.5 font-medium">
                <Sprout :size="12" class="text-accent/70"/>
                <span v-if="s.plot.crop">{{ s.plot.crop }}</span>
                <span v-if="s.plot.crop && s.plot.stage"> · </span>
                <span v-if="s.plot.stage">{{ s.plot.stage }}</span>
                <span class="text-border"> | </span>
                <span>{{ s.plot.area_ha }} ha</span>
              </div>
            </div>
            <component
              :is="healthFor(s).icon"
              :size="20"
              :class="['shrink-0 mt-1', healthFor(s).tone]"
              :stroke-width="2"
            />
          </div>

          <!-- Badges Row -->
          <div class="px-5 py-3 flex flex-wrap gap-2 min-h-[44px] items-center bg-card-hover/30">
             <span v-for="act in s.activeActuators" :key="act" class="text-[11px] font-bold uppercase tracking-wider bg-success/15 text-success border border-success/30 px-2.5 py-1 rounded-md flex items-center gap-1.5 shadow-[0_0_10px_rgba(34,197,94,0.1)]">
               <Power :size="12" class="animate-pulse" /> {{ act }} Running
             </span>
             <span v-if="s.batteryV !== null && s.batteryV < 3.5" class="text-[11px] font-bold uppercase tracking-wider bg-danger/15 text-danger border border-danger/30 px-2.5 py-1 rounded-md flex items-center gap-1.5">
               <Battery :size="12" /> Battery Low
             </span>
             <span v-if="s.activeActuators.length === 0 && (s.batteryV === null || s.batteryV >= 3.5)" class="text-[11px] font-medium text-muted flex items-center gap-1.5">
               <CheckCircle :size="12" class="text-success/60" /> All systems idle
             </span>
          </div>

          <!-- Metrics Grid -->
          <div class="grid grid-cols-4 gap-1 p-4 mt-auto">
            <div class="bg-bg/50 rounded-lg p-2.5 flex flex-col items-center justify-center border border-transparent group-hover:border-border/50 transition-colors">
              <div class="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted font-semibold mb-1">
                <Droplets :size="12" class="text-water" /> Soil
              </div>
              <div :class="['text-lg font-bold tabular-nums tracking-tight', moistureTone(s.soilMoisture)]">
                {{ s.soilMoisture !== null ? s.soilMoisture.toFixed(2) : '—' }}
              </div>
            </div>
            
            <div class="bg-bg/50 rounded-lg p-2.5 flex flex-col items-center justify-center border border-transparent group-hover:border-border/50 transition-colors">
              <div class="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted font-semibold mb-1">
                <Thermometer :size="12" class="text-warning" /> Temp
              </div>
              <div :class="['text-lg font-bold tabular-nums tracking-tight', tempTone(s.temperature)]">
                {{ s.temperature !== null ? `${s.temperature}°` : '—' }}
              </div>
            </div>
            
            <div class="bg-bg/50 rounded-lg p-2.5 flex flex-col items-center justify-center border border-transparent group-hover:border-border/50 transition-colors">
              <div class="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted font-semibold mb-1">
                <Wind :size="12" class="text-accent" /> Hum
              </div>
              <div class="text-lg font-bold tabular-nums tracking-tight text-text">
                {{ s.humidity !== null ? `${Math.round(s.humidity * 100)}%` : '—' }}
              </div>
            </div>
            
            <div class="bg-bg/50 rounded-lg p-2.5 flex flex-col items-center justify-center border border-transparent group-hover:border-border/50 transition-colors">
              <div class="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted font-semibold mb-1">
                <Clock :size="12" /> Water
              </div>
              <div class="text-[13px] font-semibold mt-1 text-text/80 text-center leading-tight">
                {{ relativeTime(s.lastWateredAt) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Empty state ───────────────────────────────────────── -->
    <section
      v-if="!loading && !plotStatuses.length"
      class="card text-center py-12 border-dashed border-2 bg-transparent"
    >
      <Sprout :size="32" :stroke-width="1.5" class="mx-auto text-muted mb-3" />
      <h3 class="font-semibold text-lg">No plots yet</h3>
      <p class="text-sm text-muted mt-1 max-w-sm mx-auto">
        Create your first plot to start monitoring sensors and getting AI advice.
      </p>
      <button
        class="btn-primary text-sm mt-6 shadow-lg shadow-accent/20"
        @click="router.push({ name: 'plots' })"
      >
        Create your first Plot
      </button>
    </section>

    <!-- ── Attention + Activity ──────────────────────────────── -->
    <div v-if="!loading" class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
      <!-- Attention -->
      <section>
        <h2 class="text-lg font-semibold mb-3 tracking-tight flex items-center gap-2">
          <AlertTriangle :size="18" class="text-warning" /> Needs attention
        </h2>
        <div class="card p-0 overflow-hidden">
          <div v-if="pendingTasks.length === 0" class="p-6 text-sm text-muted flex items-center gap-2">
            <CheckCircle :size="16" class="text-success" /> Nothing waiting on you. Good work.
          </div>

          <div
            v-for="t in pendingTasks.slice(0, 4)"
            :key="t.id"
            class="p-4 flex items-start gap-4 border-b border-border/50 last:border-0 hover:bg-card-hover/50 transition-colors"
          >
            <div class="p-2 bg-warning/10 rounded-full shrink-0">
              <Clock :size="16" class="text-warning" :stroke-width="2" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold">{{ humanTool(t.tool) }}</div>
              <p class="text-xs text-muted mt-0.5 line-clamp-2 leading-relaxed">
                {{ t.reason || 'Awaiting your approval' }}
              </p>
              <div class="text-[10px] text-muted mt-1.5 font-medium uppercase tracking-wider">
                {{ relativeTime(t.created_at) }}
              </div>
            </div>
          </div>

          <div v-if="pendingTasks.length" class="p-3 border-t border-border/50 bg-card-hover/20 text-center">
            <button
              class="text-xs font-semibold text-accent hover:text-accent-hover transition-colors flex items-center justify-center w-full gap-1 uppercase tracking-wide"
              @click="router.push({ name: 'tasks' })"
            >
              Review all tasks <ArrowRight :size="12" />
            </button>
          </div>
        </div>
      </section>

      <!-- Recent activity -->
      <section>
        <h2 class="text-lg font-semibold mb-3 tracking-tight flex items-center gap-2">
          <Activity :size="18" class="text-water" /> Recent activity
        </h2>
        <div class="card p-0 overflow-hidden">
          <div v-if="recentActivity.length === 0" class="p-6 text-sm text-muted">
            No activity yet.
          </div>

          <div
            v-for="(r, i) in recentActivity"
            :key="i"
            class="p-4 flex items-start gap-4 border-b border-border/50 last:border-0 hover:bg-card-hover/50 transition-colors"
          >
            <div class="p-2 bg-bg rounded-full shrink-0 border border-border/50">
              <component :is="r.icon" :size="14" class="text-muted" :stroke-width="2" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium">{{ r.label }}</div>
              <div v-if="r.sub" class="text-xs text-muted mt-0.5">
                {{ r.sub }}
              </div>
            </div>
            <div class="text-[10px] font-medium text-muted uppercase tracking-wider whitespace-nowrap mt-1">
              {{ relativeTime(r.at) }}
            </div>
          </div>
        </div>
      </section>
    </div>

  </div>
</template>