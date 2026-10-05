<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useChartTheme } from '../../composables/useChartTheme'

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  data: { day: string; total_lkr: number }[]
  color?: string
}>()

const theme = useChartTheme()

const color = computed(() => props.color ?? '#38BDF8')

const option = computed(() => ({
  grid: { top: 15, right: 12, bottom: 30, left: 50 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(20, 26, 24, 0.95)',
    borderColor: 'rgba(80, 90, 85, 0.5)',
    textStyle: { color: '#EBF0EE', fontSize: 12 },
    formatter: (params: any) => {
      const p = params[0]
      return `${p.axisValue}<br/><b>LKR ${Number(p.value).toFixed(2)}</b>`
    },
  },
  xAxis: {
    type: 'category',
    data: props.data.map((d) => d.day.slice(5)),
    axisLine: { lineStyle: { color: theme.border.value } },
    axisLabel: { color: theme.textMuted.value, fontSize: 11 },
    boundaryGap: false,
  },
  yAxis: {
    type: 'value',
    axisLine: { show: false },
    axisLabel: { color: theme.textMuted.value, fontSize: 11 },
    splitLine: {
      lineStyle: { color: theme.border.value, type: 'dashed', opacity: 0.5 },
    },
  },
  series: [
    {
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { color: color.value, width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: color.value + '50' },
            { offset: 1, color: color.value + '00' },
          ],
        },
      },
      data: props.data.map((d) => d.total_lkr),
    },
  ],
}))
</script>

<template>
  <VChart v-if="data.length" :option="option" style="height: 220px" autoresize />
  <div
    v-else
    class="h-[220px] flex items-center justify-center text-sm text-muted"
  >
    No spending in this period
  </div>
</template>