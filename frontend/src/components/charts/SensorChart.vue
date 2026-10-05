<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{
  title: string
  unit: string
  data: { time: string; value: number }[]
  color: string
  minValue?: number
  maxValue?: number
}>()

const option = computed(() => ({
  grid: { top: 15, right: 12, bottom: 30, left: 45 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(20, 26, 24, 0.95)',
    borderColor: 'rgba(80, 90, 85, 0.5)',
    textStyle: { color: '#EBF0EE', fontSize: 12 },
    formatter: (params: any) => {
      const p = params[0]
      const t = new Date(p.value[0]).toLocaleTimeString()
      return `${t}<br/><b>${p.value[1].toFixed(3)}</b> ${props.unit}`
    },
  },
  xAxis: {
    type: 'time',
    axisLine: { lineStyle: { color: 'var(--border)' } },
    axisLabel: { color: 'var(--text-muted)', fontSize: 10 },
    splitLine: { show: false },
  },
  yAxis: {
    type: 'value',
    min: props.minValue,
    max: props.maxValue,
    axisLine: { show: false },
    axisLabel: { color: 'var(--text-muted)', fontSize: 10 },
    splitLine: {
      lineStyle: { color: 'var(--border)', type: 'dashed', opacity: 0.5 },
    },
  },
  series: [
    {
      type: 'line',
      showSymbol: false,
      smooth: true,
      lineStyle: { color: props.color, width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: props.color + '40' },
            { offset: 1, color: props.color + '00' },
          ],
        },
      },
      data: props.data.map((d) => [d.time, d.value]),
    },
  ],
}))
</script>

<template>
  <div class="card">
    <div class="flex items-baseline justify-between mb-3">
      <h3 class="text-sm font-medium">{{ title }}</h3>
      <span
        v-if="data.length"
        class="text-lg font-semibold tabular-nums"
      >
        {{ data[data.length - 1].value.toFixed(3) }}
        <span class="text-xs text-muted font-normal ml-1">{{ unit }}</span>
      </span>
      <span v-else class="text-xs text-muted">No data yet</span>
    </div>

    <div v-if="data.length === 0" class="h-40 flex items-center justify-center text-sm text-muted">
      Waiting for readings…
    </div>

    <VChart v-else :option="option" style="height: 180px" autoresize />
  </div>
</template>