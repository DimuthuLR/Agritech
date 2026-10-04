<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, Leaf, Activity, Wallet,
  AlertTriangle, CheckCircle, XCircle, Clock,
} from 'lucide-vue-next'

import { usePlotsStore } from '../stores/plots'
import { tasksApi } from '../api/tasks'
import { diagnosesApi, type Diagnosis } from '../api/diagnoses'
import { financeApi, type CostSummary } from '../api/finance'
import { SOIL_TYPE_LABELS, type Plot } from '../types/plot'
import type { Task } from '../types/task'

const route = useRoute()
const router = useRouter()
const store = usePlotsStore()

const plotId = computed(() => route.params.id as string)
const plot = ref<Plot | null>(null)
const tasks = ref<Task[]>([])
const diagnoses = ref<Diagnosis[]>([])
const costs = ref<CostSummary | null>(null)
const loading = ref(true)

const soilLabel = computed(() =>
  plot.value ? SOIL_TYPE_LABELS[plot.value.soil_type] : ''
)

const pendingTasks = computed(() =>
  tasks.value.filter((t) => t.status === 'pending_approval')
)

const recentTasks = computed(() => tasks.value.slice(0, 5))
const recentDiagnoses = computed(() => diagnoses.value.slice(0, 3))

// Category display info
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

async function loadAll() {
  loading.value = true
  try {
    // Load plot — check cache first
    const cached = store.plots.find((p) => p.id === plotId.value)
    plot.value = cached ?? (await store.fetchOne(plotId.value))

    // Parallel fetches for related data
    const [t, d, c] = await Promise.allSettled([
      tasksApi.list(plotId.value),
      diagnosesApi.list(plotId.value),
      financeApi.plotSummary(plotId.value),
    ])
    if (t.status === 'fulfilled') tasks.value = t.value
    if (d.status === 'fulfilled') diagnoses.value = d.value
    if (c.status === 'fulfilled') costs.value = c.value
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
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

        <!-- Pending alert -->
        <div
          v-if="pendingTasks.length"
          class="pill-warning"
        >
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
              <span :class="['pill', `bg-${t.status === 'done' ? 'success' : t.status === 'pending_approval' ? 'warning' : 'muted'}/10`]">
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
            <div
              v-if="d.confidence"
              class="text-xs text-muted"
            >
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

  </div>
</template>