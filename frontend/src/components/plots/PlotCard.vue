<script setup lang="ts">
import { computed } from 'vue'
import { MapPin, Droplets } from 'lucide-vue-next'
import type { Plot } from '../../types/plot'
import { SOIL_TYPE_LABELS } from '../../types/plot'

const props = defineProps<{ plot: Plot }>()

const soilLabel = computed(() =>
  SOIL_TYPE_LABELS[props.plot.soil_type] || props.plot.soil_type
)

const cropLabel = computed(() => props.plot.crop || 'No crop assigned')

const stageLabel = computed(() => props.plot.stage || '—')

// Status: green if crop is set, muted if not.
// (Later phases will check live sensor freshness)
const hasCrop = computed(() => !!props.plot.crop)
</script>

<template>
  <router-link
    :to="{ name: 'plot-detail', params: { id: plot.id } }"
    class="card hover:bg-card-hover transition-colors
           flex flex-col gap-4 no-underline"
  >
    <!-- Header row: name + status dot -->
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h3 class="font-semibold text-base truncate">{{ plot.name }}</h3>
        <p class="text-xs text-muted truncate">{{ soilLabel }}</p>
      </div>
      <span
        :class="[
          'w-2 h-2 rounded-full shrink-0 mt-1.5',
          hasCrop ? 'bg-success' : 'bg-muted',
        ]"
        :title="hasCrop ? 'Active' : 'No crop'"
      />
    </div>

    <!-- Data rows -->
    <div class="flex flex-col gap-2 text-sm">
      <div class="flex items-center gap-2 text-text">
        <Droplets :size="14" :stroke-width="1.75" class="text-water shrink-0" />
        <span class="truncate">{{ cropLabel }}</span>
      </div>
      <div class="flex items-center gap-2 text-muted">
        <MapPin :size="14" :stroke-width="1.75" class="shrink-0" />
        <span class="truncate">{{ plot.area_ha }} ha</span>
        <span v-if="plot.stage" class="text-muted">· {{ stageLabel }}</span>
      </div>
    </div>

    <!-- Footer: hint -->
    <div class="pt-3 border-t border-border mt-auto">
      <span class="text-xs text-muted">Tap to view details →</span>
    </div>
  </router-link>
</template>