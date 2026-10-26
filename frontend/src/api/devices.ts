import { api } from './client'
import type { Device, DeviceEvent } from '../types/device'

export const devicesApi = {
  async list(): Promise<Device[]> {
    const { data } = await api.get<Device[]>('/devices')
    return data
  },

  async get(id: string): Promise<Device> {
    const { data } = await api.get<Device>(`/devices/${id}`)
    return data
  },

  // Fixed: Now accepts metadata updates for the Auto/Manual toggle
  async update(
    id: string, 
    data: { plot_id?: string | null; metadata?: Record<string, unknown> }
  ): Promise<Device> {
    const res = await api.patch<Device>(`/devices/${id}`, data)
    return res.data
  },

  async sendTestCommand(
    id: string,
    action: string,
    params: Record<string, unknown> = {}
  ) {
    const { data } = await api.post(`/devices/${id}/test-command`, { action, params })
    return data
  },

  async events(id: string, limit = 20): Promise<DeviceEvent[]> {
    const { data } = await api.get(`/devices/${id}/events`, { params: { limit } })
    return data
  }
}