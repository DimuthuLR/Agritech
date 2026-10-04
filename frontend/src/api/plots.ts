import { api } from './client'
import type { Plot, CreatePlotInput } from '../types/plot'

export const plotsApi = {
  async list(farmId?: string): Promise<Plot[]> {
    const params = farmId ? { farm_id: farmId } : {}
    const { data } = await api.get<Plot[]>('/plots', { params })
    return data
  },

  async get(id: string): Promise<Plot> {
    const { data } = await api.get<Plot>(`/plots/${id}`)
    return data
  },

  async create(input: CreatePlotInput): Promise<Plot> {
    const { data } = await api.post<Plot>('/plots', input)
    return data
  },

  async update(id: string, patch: Partial<CreatePlotInput>): Promise<Plot> {
    const { data } = await api.patch<Plot>(`/plots/${id}`, patch)
    return data
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/plots/${id}`)
  },
}