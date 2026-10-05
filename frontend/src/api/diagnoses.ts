import { api } from './client'

export interface Diagnosis {
  id: string
  tenant_id: string
  plot_id: string
  status: string
  disease: string | null
  confidence: number | null
  severity: string | null
  what_is_happening: string | null
  treatment_steps: string[] | null
  prevention_next_season: string[] | null
  estimated_cost_lkr: number | null
  calculated_cost_lkr: number | null
  recommended_ingredient: string | null
  recommended_dose_ml_per_ha: number | null
  requires_chemical: boolean
  model: string | null
  prompt_version: string | null
  created_at: string
  completed_at: string | null
}

export const diagnosesApi = {
  async list(plotId?: string): Promise<Diagnosis[]> {
    const params = plotId ? { plot_id: plotId } : {}
    const { data } = await api.get<Diagnosis[]>('/diagnosis', { params })
    return data
  },

  async get(id: string): Promise<Diagnosis> {
    const { data } = await api.get<Diagnosis>(`/diagnosis/${id}`)
    return data
  },

  async upload(
    plotId: string,
    file: File,
    notes?: string,
  ): Promise<Diagnosis> {
    const form = new FormData()
    form.append('file', file)
    form.append('plot_id', plotId)
    if (notes) form.append('notes', notes)

    const { data } = await api.post<Diagnosis>('/diagnosis/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      // Model call takes ~5s, give it room
      timeout: 60000,
    })
    return data
  },
}