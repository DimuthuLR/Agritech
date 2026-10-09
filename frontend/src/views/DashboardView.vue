<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import {
  Sprout, Droplets, Activity, Wallet, CheckSquare,
  Leaf, AlertTriangle, CheckCircle, Clock,
  Cloud, CloudRain, Sun, Wind, Thermometer,
  ArrowRight, Loader2,
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

interface SensorBucket {
  bucket: string
  device_id: string
  metric: string
  avg_value: number
  min_value: number
  max_value: number
  sample_count: number
}

interface PlotStatus {
  plot: Plot
  soilMoisture: number | null
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

const farmName = computed(() => {
  // If the first plot belongs to a farm, we could show its name
  // but we don't load farms on this page. Show tenant-less greeting.
  return 'Demo Farm'
})

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

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric',
  })
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

function weatherInfo(code: number): { icon: any; label: string } {
  if (code === 0) return { icon: Sun, label: 'Clear' }
  if (code <= 2) return { icon: Sun, label: 'Partly cloudy' }
  if (code <= 48) return { icon: Cloud, label: 'Cloudy' }
  if (code <= 67) return { icon: CloudRain, label: 'Rain' }
  if (code <= 82) return { icon: CloudRain, label: 'Showers' }
  return { icon: CloudRain, label: 'Storm' }
}

// ─── Data loading ────────────────────────────────────────────────────────
async function loadSensorsForPlot(plotId: string): Promise<{
  soilMoisture: number | null
}> {
  try {
    const { data } = await api.get<SensorBucket[]>(
      '/sensor/readings/summary',
      {
        params: {
          bucket: '1h',
          window: '6h',
          plot_id: plotId,
          metric: 'soil_moisture',
          limit: 10,
        },
      },
    )
    // Most recent bucket's avg
    if (data.length === 0) return { soilMoisture: null }
    const latest = data.reduce((a, b) =>
      a.bucket > b.bucket ? a : b,
    )
    return { soilMoisture: latest.avg_value }
  } catch {
    return { soilMoisture: null }
  }
}

async function loadWeather(lat: number, lng: number): Promise<void> {
  try {
    const url = 'https://api.open-meteo.com/v1/forecast'
    const { data } = await api.get(url, {
      baseURL: '', // bypass our API baseURL
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
    // Parallel batch — one failure doesn't kill the rest.
    const [plotsRes, tasksRes, diagRes, eventsRes, finRes] =
      await Promise.allSettled([
        api.get<Plot[]>('/plots'),
        api.get<Task[]>('/tasks'),
        api.get<Diagnosis[]>('/diagnosis', { params: { limit: 20 } }),
        api.get<FieldEvent[]>('/field-events', { params: { days: 30, limit: 20 } }),
        api.get<FinanceOverview>('/finance/overview', { params: { days: 30 } }),
      ])

    plots.value = plotsRes.status === 'fulfilled' ? plotsRes.value.data : []
    tasks.value = tasksRes.status === 'fulfilled' ? tasksRes.value.data : []
    diagnoses.value = diagRes.status === 'fulfilled' ? diagRes.value.data : []
    fieldEvents.value = eventsRes.status === 'fulfilled' ? eventsRes.value.data : []
    finance.value = finRes.status === 'fulfilled' ? finRes.value.data : null

    // Per-plot sensor fetch (soil moisture)
    const statuses: PlotStatus[] = []
    for (const p of plots.value) {
      const { soilMoisture } = await loadSensorsForPlot(p.id)

      // Last watered — most recent irrigation task marked done/acked
      const lastIrrigation = tasks.value
        .filter(
          (t) => t.plot_id === p.id &&
                 t.tool === 'control_irrigation' &&
                 (t.status === 'done' || t.status === 'acked'),
        )
        .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]

      // Latest diagnosis for this plot
      const latestDiag = diagnoses.value
        .filter((d) => d.plot_id === p.id && d.status === 'complete')
        .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null

      statuses.push({
        plot: p,
        soilMoisture,
        lastWateredAt: lastIrrigation?.created_at || null,
        latestDiagnosis: latestDiag,
      })
    }
    plotStatuses.value = statuses

    // Weather — use first plot with coordinates, else Colombo
    const withCoords = plots.value.find((p) => p.latitude && p.longitude)
    const lat = withCoords?.latitude ?? 6.9271
    const lng = withCoords?.longitude ?? 79.8612
    await loadWeather(lat, lng)

  } finally {
    loading.value = false
  }
}

onMounted(load)

// ─── UI helpers ──────────────────────────────────────────────────────────
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
      <div v-if="weather" class="card flex items-center gap-4 min-w-[220px]">
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

    <!-- ── Top stat row ──────────────────────────────────────── -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Sprout :size="14" :stroke-width="1.75" /> Plots
        </div>
        <div class="text-2xl font-semibold mt-2">{{ plots.length }}</div>
        <div class="text-xs text-muted mt-1">
          {{ totalArea.toFixed(2) }} ha total
        </div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <CheckSquare :size="14" :stroke-width="1.75" /> Pending tasks
        </div>
        <div class="text-2xl font-semibold mt-2">
          {{ pendingTasks.length }}
        </div>
        <div class="text-xs text-muted mt-1">
          {{ pendingTasks.length ? 'needs approval' : 'all clear' }}
        </div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Wallet :size="14" :stroke-width="1.75" /> Spend · 30d
        </div>
        <div class="text-2xl font-semibold mt-2">
          {{ finance ? fmtCurrency(finance.total_lkr) : '—' }}
        </div>
        <div class="text-xs text-muted mt-1">
          {{ finance?.entry_count ?? 0 }} ledger entries
        </div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs tracking-wide uppercase">
          <Leaf :size="14" :stroke-width="1.75" /> Diagnoses
        </div>
        <div class="text-2xl font-semibold mt-2">{{ diagnoses.length }}</div>
        <div class="text-xs text-muted mt-1">
          {{ recentDiagnoses.length }} recent results
        </div>
      </div>
    </div>

    <!-- ── Loading ───────────────────────────────────────────── -->
    <div v-if="loading" class="text-muted flex items-center gap-2">
      <Loader2 :size="16" class="animate-spin" /> Loading your farm…
    </div>

    <!-- ── Plots grid ───────────────────────────────────────── -->
    <section v-if="!loading && plotStatuses.length">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Your plots</h2>
        <button
          class="text-xs text-muted hover:text-text flex items-center gap-1"
          @click="router.push({ name: 'plots' })"
        >
          View all <ArrowRight :size="12" />
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="s in plotStatuses"
          :key="s.plot.id"
          class="card cursor-pointer hover:border-accent/50 transition-colors"
          @click="router.push({ name: 'plot-detail', params: { id: s.plot.id } })"
        >
          <!-- Plot header -->
          <div class="flex items-start justify-between gap-3 mb-3">
            <div class="min-w-0">
              <div class="font-semibold truncate">{{ s.plot.name }}</div>
              <div class="text-xs text-muted mt-0.5">
                <span v-if="s.plot.crop">{{ s.plot.crop }}</span>
                <span v-if="s.plot.crop && s.plot.stage"> · </span>
                <span v-if="s.plot.stage">{{ s.plot.stage }}</span>
                <span> · {{ s.plot.area_ha }} ha</span>
              </div>
            </div>
            <component
              :is="healthFor(s).icon"
              :size="18"
              :class="['shrink-0 mt-0.5', healthFor(s).tone]"
              :stroke-width="1.75"
            />
          </div>

          <!-- Quick stats -->
          <div class="grid grid-cols-3 gap-3 pt-3 border-t border-border">
            <div>
              <div class="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted">
                <Droplets :size="11" /> Soil
              </div>
              <div :class="['text-sm font-semibold tabular-nums mt-1', moistureTone(s.soilMoisture)]">
                {{ s.soilMoisture !== null ? s.soilMoisture.toFixed(2) : '—' }}
              </div>
            </div>
            <div>
              <div class="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted">
                <Clock :size="11" /> Last water
              </div>
              <div class="text-sm font-medium mt-1">
                {{ relativeTime(s.lastWateredAt) }}
              </div>
            </div>
            <div>
              <div class="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted">
                <Leaf :size="11" /> Health
              </div>
              <div :class="['text-xs font-medium mt-1 truncate', healthFor(s).tone]">
                {{ healthFor(s).label }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Empty state ───────────────────────────────────────── -->
    <section
      v-if="!loading && !plotStatuses.length"
      class="card text-center py-10"
    >
      <Sprout :size="28" :stroke-width="1.5" class="mx-auto text-muted mb-3" />
      <h3 class="font-semibold">No plots yet</h3>
      <p class="text-sm text-muted mt-1">
        Create your first plot to start monitoring sensors and getting AI advice.
      </p>
      <button
        class="btn-primary text-sm mt-4"
        @click="router.push({ name: 'plots' })"
      >
        Go to Plots
      </button>
    </section>

    <!-- ── Attention + Activity ──────────────────────────────── -->
    <div v-if="!loading" class="grid grid-cols-1 md:grid-cols-2 gap-4">

      <!-- Attention -->
      <section>
        <h2 class="text-lg font-semibold mb-3">Needs attention</h2>
        <div class="card space-y-3">
          <div v-if="pendingTasks.length === 0" class="text-sm text-muted">
            Nothing waiting on you. Good work.
          </div>

          <div
            v-for="t in pendingTasks.slice(0, 4)"
            :key="t.id"
            class="flex items-start gap-3 pb-3 border-b border-border last:pb-0 last:border-b-0"
          >
            <Clock :size="16" class="text-warning shrink-0 mt-0.5" :stroke-width="1.75" />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium">{{ humanTool(t.tool) }}</div>
              <p class="text-xs text-muted mt-0.5 line-clamp-2">
                {{ t.reason || 'Awaiting your approval' }}
              </p>
              <div class="text-[10px] text-muted mt-1">
                {{ relativeTime(t.created_at) }}
              </div>
            </div>
          </div>

          <button
            v-if="pendingTasks.length"
            class="text-xs text-accent hover:underline flex items-center gap-1"
            @click="router.push({ name: 'tasks' })"
          >
            Review all <ArrowRight :size="12" />
          </button>
        </div>
      </section>

      <!-- Recent activity -->
      <section>
        <h2 class="text-lg font-semibold mb-3">Recent activity</h2>
        <div class="card space-y-3">
          <div v-if="recentActivity.length === 0" class="text-sm text-muted">
            No activity yet.
          </div>

          <div
            v-for="(r, i) in recentActivity"
            :key="i"
            class="flex items-start gap-3"
          >
            <component
              :is="r.icon"
              :size="16"
              class="text-muted shrink-0 mt-0.5"
              :stroke-width="1.75"
            />
            <div class="flex-1 min-w-0">
              <div class="text-sm">{{ r.label }}</div>
              <div v-if="r.sub" class="text-xs text-muted mt-0.5">
                {{ r.sub }}
              </div>
            </div>
            <div class="text-[10px] text-muted whitespace-nowrap">
              {{ relativeTime(r.at) }}
            </div>
          </div>
        </div>
      </section>
    </div>

  </div>
</template>