import { api } from './client'

export interface Farm {
  id: string
  tenant_id: string
  name: string
  region: string
  timezone: string
  created_at: string
  updated_at: string
}

export const farmsApi = {
  async list(): Promise<Farm[]> {
    const { data } = await api.get<Farm[]>('/farms')
    return data
  },

  async get(id: string): Promise<Farm> {
    const { data } = await api.get<Farm>(`/farms/${id}`)
    return data
  },
}