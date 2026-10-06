<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { Wallet, TrendingUp, Layers } from 'lucide-vue-next'
import { useFinanceStore } from '../stores/finance'
import { CATEGORY_META } from '../api/finance'
import { defineAsyncComponent } from 'vue'
const DonutChart = defineAsyncComponent(
  () => import('../components/charts/DonutChart.vue')
)
const TrendChart = defineAsyncComponent(
  () => import('../components/charts/TrendChart.vue')
)

const store = useFinanceStore()

const ranges = [
  { days: 7,  label: '7d' },
  { days: 30, label: '30d' },
  { days: 90, label: '90d' },
]

const slices = computed(() => {
  if (!store.overview) return []
  return Object.entries(store.overview.breakdown)
    .filter(([_, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([k, v]) => ({
      label: CATEGORY_META[k]?.label ?? k,
      value: v,
      color: CATEGORY_META[k]?.color ?? '#6B7280',
    }))
})

const topPlot = computed(() => store.overview?.by_plot[0] ?? null)

onMounted(async () => {
  await store.fetchOverview()
  await store.fetchLedger()
})

function setRange(days: number) {
  store.fetchOverview(days)
}
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- Header -->
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-2xl font-semibold">Finance</h1>
        <p class="text-muted text-sm mt-1">
          Costs from your executed tasks
        </p>
      </div>

      <!-- Time range selector -->
      <div class="flex items-center rounded-sm border border-border overflow-hidden">
        <button
          v-for="r in ranges"
          :key="r.days"
          :class="[
            'px-3 py-1.5 text-sm transition-colors',
            store.days === r.days
              ? 'bg-accent text-invert'
              : 'text-muted hover:text-text hover:bg-card-hover',
          ]"
          @click="setRange(r.days)"
        >
          {{ r.label }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="store.loading && !store.overview" class="card text-sm text-muted">
      Loading costs…
    </div>

    <template v-else-if="store.overview">
      <!-- Summary tiles -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="card">
          <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
            <Wallet :size="14" :stroke-width="1.75" />
            Total spend
          </div>
          <div class="text-2xl font-semibold mt-2">
            LKR {{ store.overview.total_lkr.toFixed(0) }}
          </div>
          <div class="text-xs text-muted mt-1">
            last {{ store.overview.window_days }} days
          </div>
        </div>

        <div class="card">
          <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
            <TrendingUp :size="14" :stroke-width="1.75" />
            Entries
          </div>
          <div class="text-2xl font-semibold mt-2">
            {{ store.overview.entry_count }}
          </div>
          <div class="text-xs text-muted mt-1">
            recorded cost events
          </div>
        </div>

        <div class="card">
          <div class="flex items-center gap-2 text-muted text-xs uppercase tracking-wide">
            <Layers :size="14" :stroke-width="1.75" />
            Top plot
          </div>
          <div class="text-2xl font-semibold mt-2 truncate">
            {{ topPlot ? topPlot.name : '—' }}
          </div>
          <div class="text-xs text-muted mt-1">
            <template v-if="topPlot">
              LKR {{ topPlot.total_lkr.toFixed(0) }} spent
            </template>
            <template v-else>no plot spending yet</template>
          </div>
        </div>
      </div>

      <!-- Two-chart row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="card">
          <h2 class="text-sm font-medium mb-4">By category</h2>
          <DonutChart v-if="slices.length" :slices="slices" />
          <div v-else class="h-[220px] flex items-center justify-center text-sm text-muted">
            No spending to break down
          </div>
          <div v-if="slices.length" class="mt-4 space-y-2">
            <div
              v-for="s in slices"
              :key="s.label"
              class="flex items-center gap-2 text-sm"
            >
              <span
                class="w-2.5 h-2.5 rounded-full shrink-0"
                :style="{ backgroundColor: s.color }"
              />
              <span class="flex-1 text-muted">{{ s.label }}</span>
              <span class="tabular-nums">LKR {{ s.value.toFixed(0) }}</span>
            </div>
          </div>
        </div>

        <div class="card">
          <h2 class="text-sm font-medium mb-4">Daily trend</h2>
          <TrendChart :data="store.overview.trend" />
        </div>
      </div>

      <!-- Per-plot list -->
      <div v-if="store.overview.by_plot.length">
        <h2 class="text-sm font-medium mb-3 text-muted uppercase tracking-wide">
          By plot
        </h2>
        <div class="card p-0 divide-y divide-border">
          <div
            v-for="p in store.overview.by_plot"
            :key="p.plot_id"
            class="p-4 flex items-center justify-between gap-4"
          >
            <router-link
              :to="{ name: 'plot-detail', params: { id: p.plot_id } }"
              class="flex-1 min-w-0"
            >
              <div class="font-medium text-sm hover:text-accent">
                {{ p.name }}
              </div>
            </router-link>
            <div class="text-sm tabular-nums font-medium">
              LKR {{ p.total_lkr.toFixed(0) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Ledger entries -->
      <div v-if="store.ledger.length">
        <h2 class="text-sm font-medium mb-3 text-muted uppercase tracking-wide">
          Recent entries
        </h2>
        <div class="card p-0 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-border text-left text-muted">
                <th class="px-4 py-3 font-normal">When</th>
                <th class="px-4 py-3 font-normal">Plot</th>
                <th class="px-4 py-3 font-normal">Category</th>
                <th class="px-4 py-3 font-normal text-right">Qty</th>
                <th class="px-4 py-3 font-normal text-right">Cost</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              <tr
                v-for="e in store.ledger"
                :key="e.id"
                class="hover:bg-card-hover"
              >
                <td class="px-4 py-3 text-muted whitespace-nowrap">
                  {{ new Date(e.occurred_at).toLocaleString() }}
                </td>
                <td class="px-4 py-3 truncate max-w-xs">{{ e.plot_name }}</td>
                <td class="px-4 py-3">
                  <span
                    class="pill text-xs"
                    :style="{
                      backgroundColor: (CATEGORY_META[e.category]?.color ?? '#6B7280') + '20',
                      color: CATEGORY_META[e.category]?.color ?? '#6B7280',
                    }"
                  >
                    {{ CATEGORY_META[e.category]?.label ?? e.category }}
                  </span>
                </td>
                <td class="px-4 py-3 text-right tabular-nums text-muted">
                  {{ e.qty.toFixed(2) }} {{ e.unit }}
                </td>
                <td class="px-4 py-3 text-right tabular-nums font-medium">
                  LKR {{ e.amount_lkr.toFixed(2) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Empty state -->
    <div
      v-else-if="!store.loading"
      class="card flex flex-col items-center gap-3 py-12 text-center"
    >
      <Wallet :size="32" :stroke-width="1.5" class="text-muted" />
      <div>
        <h3 class="font-medium">No costs yet</h3>
        <p class="text-sm text-muted mt-1">
          Costs appear here after tasks are dispatched and completed.
        </p>
      </div>
    </div>

  </div>
</template>