import { defineStore } from 'pinia'
import { ref } from 'vue'
import { diagnosesApi, type Diagnosis } from '../api/diagnoses'

export const useDiagnosesStore = defineStore('diagnoses', () => {
  const items = ref<Diagnosis[]>([])
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll(plotId?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      items.value = await diagnosesApi.list(plotId)
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Failed to load diagnoses'
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function upload(
    plotId: string,
    file: File,
    notes?: string,
  ): Promise<Diagnosis | null> {
    uploading.value = true
    error.value = null
    try {
      const diag = await diagnosesApi.upload(plotId, file, notes)
      items.value.unshift(diag)
      return diag
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Diagnosis failed'
      return null
    } finally {
      uploading.value = false
    }
  }

  return { items, loading, uploading, error, fetchAll, upload }
})