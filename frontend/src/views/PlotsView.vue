<script setup lang="ts">
import { onMounted, ref, computed, watch, onUnmounted } from 'vue'
import { Plus, Sprout } from 'lucide-vue-next'
import { usePlotsStore } from '../stores/plots'
import { devicesApi } from '../api/devices'
import { api } from '../api/client'
import PlotCard from '../components/plots/PlotCard.vue'
import CreatePlotModal from '../components/plots/CreatePlotModal.vue'

const store = usePlotsStore()
const showCreate = ref(false)
const loadingDevices = ref(true)

const livePlotData = ref<Record<string, any>>({})
let pollInterval: any = null

watch(() => store.plots.length, async (newLength) => {
  if (newLength > 0) {
    await loadLiveData()
  }
}, { immediate: true })

onMounted(async () => {
  await store.fetchAll()
  pollInterval = setInterval(loadLiveData, 5000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})

const totalArea = computed(() => store.totalAreaHa.toFixed(2))

const gridClass = computed(() => {
  if (store.count === 1) return 'grid grid-cols-1 max-w-2xl mx-auto gap-6'
  return 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6'
})

async function loadLiveData() {
  if (Object.keys(livePlotData.value).length === 0) {
    loadingDevices.value = true
  }
  
  try {
    const devices = await devicesApi.list()
    const dataMap: Record<string, any> = {}
    
    for (const p of store.plots) {
      const plotDevices = devices.filter(d => String(d.plot_id) === String(p.id))
      const plotSensors = plotDevices.filter(d => d.kind === 'sensor')
      const plotActuators = plotDevices.filter(d => d.kind === 'actuator')

      let metrics: Record<string, number> = {}
      let lastSeen: string | null = null

      // 1. Fetch latest standard sensor readings
      try {
        const { data: readings } = await api.get('/sensor/readings', {
          params: { plot_id: p.id, limit: 20 }
        })
        const seen = new Set()
        for (const r of readings) {
          if (!lastSeen || new Date(r.time) > new Date(lastSeen)) lastSeen = r.time
          if (seen.has(r.metric)) continue
          seen.add(r.metric)
          metrics[r.metric] = r.value
        }
      } catch (e) {}

      // 2. Fetch specifically for pump_state and valve_state by PLOT ID
      try {
        const { data: pData } = await api.get('/sensor/readings', { 
          params: { plot_id: p.id, metric: 'pump_state', limit: 1 } 
        })
        if (pData.length > 0) metrics['pump_state'] = pData[0].value

        const { data: vData } = await api.get('/sensor/readings', { 
          params: { plot_id: p.id, metric: 'valve_state', limit: 1 } 
        })
        if (vData.length > 0) metrics['valve_state'] = vData[0].value
      } catch (e) {}

      dataMap[p.id] = {
        metrics,
        sensors: plotSensors,
        actuators: plotActuators,
        lastSeen
      }
    }
    
    livePlotData.value = dataMap
  } finally {
    loadingDevices.value = false
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold">Plots</h1>
        <p class="text-muted text-sm mt-1">
          <template v-if="store.count">
            {{ store.count }} plot{{ store.count === 1 ? '' : 's' }} · {{ totalArea }} ha total
          </template>
          <template v-else>Your growing areas</template>
        </p>
      </div>
      <button class="btn-primary" @click="showCreate = true">
        <Plus :size="16" :stroke-width="2" /> New plot
      </button>
    </div>

    <div v-if="store.loading || loadingDevices" class="card text-muted text-sm flex items-center gap-2">
      <span class="animate-spin h-4 w-4 border-2 border-muted border-t-transparent rounded-full"></span>
      Loading plots and live hardware…
    </div>
    <div v-else-if="store.error" class="card border-danger/40 text-danger text-sm">{{ store.error }}</div>
    <div v-else-if="store.count === 0" class="card flex flex-col items-center gap-4 py-12 text-center">
      <div class="w-12 h-12 rounded-full bg-accent-soft text-accent flex items-center justify-center">
        <Sprout :size="24" :stroke-width="1.75" />
      </div>
      <div>
        <h3 class="font-medium">No plots yet</h3>
        <p class="text-sm text-muted mt-1">Create your first plot to start monitoring.</p>
      </div>
      <button class="btn-primary" @click="showCreate = true">
        <Plus :size="16" :stroke-width="2" /> Create your first plot
      </button>
    </div>

    <div v-else :class="gridClass">
      <PlotCard 
        v-for="p in store.plots" 
        :key="p.id" 
        :plot="p" 
        :live="livePlotData[p.id]"
      />
    </div>

    <CreatePlotModal :open="showCreate" @close="showCreate = false" @created="showCreate = false" />
  </div>
</template>