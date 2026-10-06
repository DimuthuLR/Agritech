<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, Leaf, Activity, Wallet,
  AlertTriangle, CheckCircle, XCircle, Clock,
  ClipboardList, Plus, Check, X as XIcon,
} from 'lucide-vue-next'
import { usePlotsStore } from '../stores/plots'
import { tasksApi } from '../api/tasks'
import { diagnosesApi, type Diagnosis } from '../api/diagnoses'
import { financeApi, type CostSummary } from '../api/finance'
import { fieldEventsApi, type FieldEvent } from '../api/field_events'
import { sensorsApi } from '../api/sensors'
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

const plotId = computed(() => route.params.id as string)
const plot = ref<Plot | null>(null)
const tasks = ref<Task[]>([])
const diagnoses = ref<Diagnosis[]>([])
const costs = ref<CostSummary | null>(null)
const fieldEvents = ref<FieldEvent[]>([])
const showOverrideModal = ref(false)
const loading = ref(true)

const soilLabel = computed(() =>
  plot.value ? SOIL_TYPE_LABELS[plot.value.soil_type] : ''
)

const pendingTasks = computed(() =>
  tasks.value.filter((t) => t.status === 'pending_approval')
)

const recentTasks = computed(() => tasks.value.slice(0, 5))
const recentDiagnoses = computed(() =>
  diagnoses.value
    .filter((d) => d.status === 'complete')
    .slice(0, 3),
)
// --- Live sensor stream ---
const sensors = useSensorStream(plotId.value)

const soilData = computed(() => sensors.series.value.soil_moisture ?? [])
const tempData = computed(() => sensors.series.value.temperature ?? [])
const humidData = computed(() => sensors.series.value.humidity ?? [])

// --- Cost category display ---
const CATEGORY_LABELS: Record<string, string> = {
  water: 'Water',
  fertilizer: 'Fertilizer',
  chemical: 'Chemical',
  labor: 'Labor',
  energy: 'Energy',
  fuel: 'Fuel',
  seed: 'Seed',
  equipment: 'Equipment',
  other: 'Other',
}

const costRows = computed(() => {
  if (!costs.value) return []
  return Object.entries(costs.value.breakdown)
    .filter(([_, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([k, v]) => ({
      key: k,
      label: CATEGORY_LABELS[k] || k,
      value: v,
    }))
})

function statusIcon(status: string) {
  switch (status) {
    case 'done': return CheckCircle
    case 'pending_approval': return Clock
    case 'rejected':
    case 'failed': return XCircle
    case 'dispatched':
    case 'acked':
    case 'approved': return Activity
    default: return AlertTriangle
  }
}

function statusColor(status: string) {
  switch (status) {
    case 'done': return 'text-success'
    case 'pending_approval': return 'text-warning'
    case 'rejected':
    case 'failed': return 'text-danger'
    default: return 'text-water'
  }
}

function actionLabel(tool: string | null): string {
  if (!tool) return 'Action'
  const labels: Record<string, string> = {
    control_irrigation: 'Irrigation',
    schedule_fertigation: 'Fertigation',
    spray_chemical: 'Chemical spray',
    other: 'Other action',
  }
  return labels[tool] || tool
}

function onOverrideCreated(event: FieldEvent) {
  fieldEvents.value = [event, ...fieldEvents.value]
}

async function loadAll() {
  loading.value = true
  try {
    // Load plot — check cache first
    const cached = store.plots.find((p) => p.id === plotId.value)
    plot.value = cached ?? (await store.fetchOne(plotId.value))

    // Parallel fetches for related data
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
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 1. Load plot metadata, tasks, diagnoses, costs, overrides
  loadAll()

  // 2. Load 24h of hourly sensor history (from continuous aggregates).
  //    This runs in parallel with the WebSocket connect — whichever
  //    completes first, the seed() merge handles both orderings.
  sensorsApi
    .summary(plotId.value, '1h', '24h')
    .then((buckets) => {
      // Group buckets by metric
      const byMetric: Record<string, { time: string; value: number }[]> = {}
      for (const b of buckets) {
        ;(byMetric[b.metric] ??= []).push({
          time: b.bucket,
          value: b.avg_value,
        })
      }
      // Seed each metric's chart series
      for (const [metric, points] of Object.entries(byMetric)) {
        sensors.seed(metric, points)
      }
    })
    .catch(() => {
      // Silent — the live stream will still populate as data arrives
    })

  // 3. Connect the live stream
  sensors.connect()
})
</script>

<template>
  <div class="max-w-5xl mx-auto space-y-6">

    <!-- Back + Header -->
    <div>
      <button
        class="text-muted hover:text-text text-sm inline-flex items-center gap-1 mb-3"
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
          {{ pendingTasks.length }} pending
          task{{ pendingTasks.length === 1 ? '' : 's' }}
        </div>
      </div>
    </div>

    <!-- Summary tiles -->
    <div v-if="!loading && plot" class="grid grid-cols-1 sm:grid-cols-3 gap-4">

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Leaf :size="14" :stroke-width="1.75" />
          Crop
        </div>
        <div class="text-2xl font-semibold mt-2">
          {{ plot.crop || '—' }}
        </div>
        <div class="text-xs text-muted mt-1">
          {{ plot.stage || 'no stage set' }}
        </div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Activity :size="14" :stroke-width="1.75" />
          Recent tasks
        </div>
        <div class="text-2xl font-semibold mt-2">
          {{ tasks.length }}
        </div>
        <div class="text-xs text-muted mt-1">
          {{ pendingTasks.length }} awaiting approval
        </div>
      </div>

      <div class="card">
        <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
          <Wallet :size="14" :stroke-width="1.75" />
          Total cost
        </div>
        <div class="text-2xl font-semibold mt-2">
          LKR {{ costs?.total_lkr?.toFixed(0) || '0' }}
        </div>
        <div class="text-xs text-muted mt-1">
          all time
        </div>
      </div>
    </div>

    <!-- Live sensor charts -->
    <section v-if="!loading && plot">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Live sensors</h2>
        <span
          :class="[
            'pill text-xs',
            sensors.connected.value
              ? 'bg-success/10 text-success'
              : 'bg-muted/10 text-muted',
          ]"
        >
          <span
            :class="[
              'w-1.5 h-1.5 rounded-full',
              sensors.connected.value ? 'bg-success animate-pulse' : 'bg-muted',
            ]"
          />
          {{ sensors.connected.value ? 'Live' : 'Connecting…' }}
        </span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <SensorChart
          title="Soil moisture"
          unit=""
          :data="soilData"
          color="#38BDF8"
          :min-value="0"
          :max-value="1"
        />
        <SensorChart
          title="Temperature"
          unit="°C"
          :data="tempData"
          color="#F59E0B"
        />
        <SensorChart
          title="Humidity"
          unit=""
          :data="humidData"
          color="#34D399"
          :min-value="0"
          :max-value="1"
        />
      </div>
    </section>

    <!-- Recent Tasks -->
    <section v-if="!loading && plot">
      <h2 class="text-lg font-semibold mb-3">Recent tasks</h2>
      <div v-if="recentTasks.length === 0" class="card text-sm text-muted">
        No tasks yet for this plot.
      </div>
      <div v-else class="card p-0 divide-y divide-border">
        <div
          v-for="t in recentTasks"
          :key="t.id"
          class="p-4 flex items-start gap-3"
        >
          <component
            :is="statusIcon(t.status)"
            :size="18" :stroke-width="1.75"
            :class="['shrink-0 mt-0.5', statusColor(t.status)]"
          />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-medium text-sm">{{ t.tool }}</span>
              <span class="pill bg-card-hover text-muted text-xs">
                {{ t.status }}
              </span>
            </div>
            <p class="text-xs text-muted mt-1 line-clamp-2">{{ t.reason }}</p>
            <p class="text-xs text-muted mt-1">
              {{ new Date(t.created_at).toLocaleString() }}
            </p>
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
        <div
          v-for="d in recentDiagnoses"
          :key="d.id"
          class="card"
        >
          <div class="flex items-start justify-between gap-2 mb-2">
            <div>
              <div class="font-medium text-sm">{{ d.disease || 'Unknown' }}</div>
              <div class="text-xs text-muted">
                {{ d.severity || '—' }} severity
              </div>
            </div>
            <div v-if="d.confidence" class="text-xs text-muted">
              {{ Math.round(d.confidence * 100) }}%
            </div>
          </div>
          <div class="text-xs text-muted">
            Cost:
            <span class="text-text font-medium">
              LKR {{ (d.calculated_cost_lkr || d.estimated_cost_lkr || 0).toFixed(0) }}
            </span>
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
        <div
          v-for="row in costRows"
          :key="row.key"
          class="flex items-center gap-3"
        >
          <div class="w-24 text-sm text-muted">{{ row.label }}</div>
          <div class="flex-1 h-2 bg-card-hover rounded-full overflow-hidden">
            <div
              class="h-full bg-water rounded-full transition-all"
              :style="{ width: `${(row.value / costs!.total_lkr) * 100}%` }"
            />
          </div>
          <div class="w-24 text-right text-sm tabular-nums">
            LKR {{ row.value.toFixed(0) }}
          </div>
        </div>
      </div>
    </section>

    <!-- Overrides / self-recorded actions -->
    <section v-if="!loading && plot">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Our own actions</h2>
        <button
          class="btn-ghost text-xs py-1.5 px-3"
          @click="showOverrideModal = true"
        >
          <Plus :size="14" :stroke-width="2" />
          Record action
        </button>
      </div>

      <div
        v-if="fieldEvents.length === 0"
        class="card text-sm text-muted text-center py-6"
      >
        <ClipboardList :size="20" :stroke-width="1.5" class="mx-auto mb-2" />
        <p>
          When you act against the platform's advice, record it here.
          The AI learns from your experience.
        </p>
      </div>

      <div v-else class="card p-0 divide-y divide-border">
        <div
          v-for="e in fieldEvents.slice(0, 5)"
          :key="e.id"
          class="p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">
                  {{ actionLabel(e.action_taken) }}
                </span>

                <span
                  v-if="e.outcome === 'worked'"
                  class="pill-success text-xs"
                >
                  <Check :size="11" :stroke-width="2" />
                  Justified
                </span>
                <span
                  v-else-if="e.outcome === 'failed'"
                  class="pill-danger text-xs"
                >
                  <XIcon :size="11" :stroke-width="2" />
                  Not justified
                </span>
                <span
                  v-else
                  class="pill-muted text-xs"
                >
                  <Clock :size="11" :stroke-width="2" />
                  Awaiting verification
                </span>
              </div>

              <p class="text-xs text-muted mt-1.5 line-clamp-2">
                {{ e.reason }}
              </p>
            </div>
            <span class="text-xs text-muted shrink-0">
              {{ new Date(e.occurred_at).toLocaleDateString() }}
            </span>
          </div>

          <div
            v-if="e.weather_forecast_mm !== null && e.weather_actual_mm !== null"
            class="mt-2 text-xs text-muted"
          >
            Forecast {{ e.weather_forecast_mm.toFixed(1) }}mm ·
            Actual {{ e.weather_actual_mm.toFixed(1) }}mm
          </div>
        </div>
      </div>
    </section>

    <!-- Modal -->
    <RecordOverrideModal
      :open="showOverrideModal"
      :plot-id="plotId"
      @close="showOverrideModal = false"
      @created="onOverrideCreated"
    />

  </div>
</template>