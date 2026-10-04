import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { plotsApi } from '../api/plots'
import type { Plot, CreatePlotInput } from '../types/plot'

export const usePlotsStore = defineStore('plots', () => {
  const plots = ref<Plot[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const count = computed(() => plots.value.length)

  // Group by crop for summary stats
  const byCrop = computed(() => {
    const groups: Record<string, number> = {}
    for (const p of plots.value) {
      const crop = p.crop || 'unassigned'
      groups[crop] = (groups[crop] || 0) + 1
    }
    return groups
  })

  // Total area across all plots
  const totalAreaHa = computed(() =>
    plots.value.reduce((sum, p) => sum + (p.area_ha || 0), 0)
  )

  async function fetchAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      plots.value = await plotsApi.list()
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Failed to load plots'
      plots.value = []
    } finally {
      loading.value = false
    }
  }

  async function fetchOne(id: string): Promise<Plot | null> {
    try {
      const plot = await plotsApi.get(id)
      // Update local cache if we have it
      const idx = plots.value.findIndex((p) => p.id === id)
      if (idx >= 0) plots.value[idx] = plot
      else plots.value.push(plot)
      return plot
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Failed to load plot'
      return null
    }
  }

  async function create(input: CreatePlotInput): Promise<Plot | null> {
    try {
      const plot = await plotsApi.create(input)
      plots.value.push(plot)
      return plot
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Failed to create plot'
      return null
    }
  }

  function reset() {
    plots.value = []
    error.value = null
  }

  return {
    plots, loading, error,
    count, byCrop, totalAreaHa,
    fetchAll, fetchOne, create, reset,
  }
})