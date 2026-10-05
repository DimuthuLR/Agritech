<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartTheme } from '../../composables/useChartTheme'

use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer])

interface Slice {
  label: string
  value: number
  color: string
}

const props = defineProps<{ slices: Slice[] }>()

const theme = useChartTheme()

const total = computed(() =>
  props.slices.reduce((sum, s) => sum + s.value, 0)
)

const option = computed(() => ({
  tooltip: {
    trigger: 'item',
    backgroundColor: 'rgba(20, 26, 24, 0.95)',
    borderColor: 'rgba(80, 90, 85, 0.5)',
    textStyle: { color: '#EBF0EE', fontSize: 12 },
    formatter: (p: any) =>
      `${p.name}<br/><b>LKR ${Number(p.value).toFixed(2)}</b> (${p.percent}%)`,
  },
  series: [
    {
      type: 'pie',
      radius: ['62%', '88%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderColor: theme.card.value,
        borderWidth: 2,
      },
      label: { show: false },
      labelLine: { show: false },
      data: props.slices.map((s) => ({
        name: s.label,
        value: s.value,
        itemStyle: { color: s.color },
      })),
    },
  ],
}))
</script>

<template>
  <div class="relative">
    <VChart :option="option" style="height: 220px" autoresize />
    <div
      class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
    >
      <div class="text-xs text-muted uppercase tracking-wide">Total</div>
      <div class="text-xl font-semibold mt-0.5">
        LKR {{ total.toFixed(0) }}
      </div>
    </div>
  </div>
</template>