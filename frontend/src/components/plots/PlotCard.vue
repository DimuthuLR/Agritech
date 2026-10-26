<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { 
  MapPin, Droplets, Thermometer, 
  Power, Battery, WifiOff
} from 'lucide-vue-next'
import type { Plot } from '../../types/plot'
import { SOIL_TYPE_LABELS } from '../../types/plot'
import type { Device } from '../../types/device'

const props = defineProps<{ 
  plot: Plot
  live?: { 
    metrics: Record<string, number>
    sensors: Device[]
    actuators: Device[]
    lastSeen: string | null
  }
}>()

const router = useRouter()

const soilLabel = computed(() => SOIL_TYPE_LABELS[props.plot.soil_type] || props.plot.soil_type)
const cropLabel = computed(() => props.plot.crop || 'No crop assigned')
const stageLabel = computed(() => props.plot.stage || '—')
const hasCrop = computed(() => !!props.plot.crop)

// Warnings
const isOffline = computed(() => {
  if (!props.live?.lastSeen) return true
  const seen = new Date(props.live.lastSeen).getTime()
  return (Date.now() - seen) / 1000 > 15 * 60 // 15 mins
})

const hasLowBattery = computed(() => {
  return props.live?.sensors?.some(s => s.battery_v !== null && s.battery_v < 3.5) || false
})

// Safely cast to Number to avoid string/float mismatch
const isPumpRunning = computed(() => Number(props.live?.metrics?.pump_state) === 1)
const isValveOpen = computed(() => Number(props.live?.metrics?.valve_state) === 1)

function moistureTone(v: number | undefined): string {
  if (v === undefined) return 'text-muted'
  if (v < 0.30) return 'text-danger'
  if (v < 0.50) return 'text-warning'
  return 'text-success'
}

function goToDetail() {
  router.push({ name: 'plot-detail', params: { id: props.plot.id } })
}
</script>

<template>
  <div 
    @click="goToDetail"
    class="card group cursor-pointer hover:border-accent/40 hover:shadow-lg hover:shadow-accent/5 transition-all duration-300 flex flex-col p-0 overflow-hidden"
  >
    <!-- Header -->
    <div class="p-5 pb-4 flex items-start justify-between gap-3 border-b border-border/50">
      <div class="min-w-0">
        <h3 class="text-lg font-bold truncate tracking-tight group-hover:text-accent transition-colors">
          {{ plot.name }}
        </h3>
        <p class="text-xs text-muted truncate mt-0.5">{{ soilLabel }}</p>
      </div>
      <span :class="['w-2.5 h-2.5 rounded-full shrink-0 mt-1.5', hasCrop ? 'bg-success' : 'bg-muted']" />
    </div>

    <!-- Warnings & Active States -->
    <div v-if="isOffline || hasLowBattery || isPumpRunning || isValveOpen" class="px-5 pt-3 pb-1 flex flex-wrap gap-2">
      <span v-if="isOffline" class="text-[10px] font-bold uppercase tracking-wider bg-muted/20 text-muted px-2 py-0.5 rounded border border-border flex items-center gap-1">
        <WifiOff :size="10" /> Offline
      </span>
      <span v-if="hasLowBattery" class="text-[10px] font-bold uppercase tracking-wider bg-danger/15 text-danger px-2 py-0.5 rounded border border-danger/30 flex items-center gap-1">
        <Battery :size="10" /> Low Battery
      </span>
      <span v-if="isPumpRunning" class="text-[10px] font-bold uppercase tracking-wider bg-success/15 text-success px-2 py-0.5 rounded border border-success/30 flex items-center gap-1 shadow-[0_0_10px_rgba(34,197,94,0.1)]">
        <Power :size="10" class="animate-pulse" /> Pump Running
      </span>
      <span v-if="isValveOpen" class="text-[10px] font-bold uppercase tracking-wider bg-warning/15 text-warning px-2 py-0.5 rounded border border-warning/30 flex items-center gap-1">
        <Power :size="10" /> Valve Open
      </span>
    </div>

    <!-- Live Data Grid -->
    <div class="px-5 py-4 grid grid-cols-2 gap-3 bg-card-hover/20 mt-auto">
      <div class="flex items-center gap-2.5">
        <div class="p-2 bg-water/10 rounded-md">
          <Droplets :size="16" class="text-water" />
        </div>
        <div>
          <div class="text-[10px] uppercase tracking-wider text-muted font-semibold">Moisture</div>
          <div :class="['text-sm font-bold tabular-nums', moistureTone(live?.metrics?.soil_moisture)]">
            {{ live?.metrics?.soil_moisture !== undefined ? live.metrics.soil_moisture.toFixed(2) : '—' }}
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2.5">
        <div class="p-2 bg-warning/10 rounded-md">
          <Thermometer :size="16" class="text-warning" />
        </div>
        <div>
          <div class="text-[10px] uppercase tracking-wider text-muted font-semibold">Temp</div>
          <div class="text-sm font-bold tabular-nums">
            {{ live?.metrics?.temperature !== undefined ? `${live.metrics.temperature}°` : '—' }}
          </div>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="p-5 pt-4 border-t border-border/50 flex items-center justify-between gap-3">
      <div class="min-w-0">
        <div class="text-sm font-medium truncate flex items-center gap-1.5">
          <span class="text-accent/70">🌱</span> {{ cropLabel }}
        </div>
        <div class="text-[11px] text-muted truncate mt-0.5 flex items-center gap-1">
          <MapPin :size="10" /> {{ plot.area_ha }} ha <span v-if="plot.stage">· {{ stageLabel }}</span>
        </div>
      </div>
    </div>
  </div>
</template>