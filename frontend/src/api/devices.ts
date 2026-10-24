import { api } from './client'
import type { Device, DeviceEvent, TestCommandResponse } from '../types/device'

export const devicesApi = {
  async list(params?: { plot_id?: string; kind?: string }): Promise<Device[]> {
    const { data } = await api.get<Device[]>('/devices', { params })
    return data
    
    
  },

  async get(id: string): Promise<Device> {
    const { data } = await api.get<Device>(`/devices/${id}`)
    return data
  },

  async sendTestCommand(
    id: string,
    action: string,
    params: Record<string, unknown> = {},
  ): Promise<TestCommandResponse> {
    const { data } = await api.post<TestCommandResponse>(
      `/devices/${id}/test-command`,
      { action, params },
    )
    return data
  },

  async events(id: string, limit = 20): Promise<DeviceEvent[]> {
    const { data } = await api.get<DeviceEvent[]>(
      `/devices/${id}/events`,
      { params: { limit } },
    )
    return data
  },

  async update(id: string, data: { plot_id?: string | null }): Promise<Device> {
    const res = await api.patch<Device>(`/devices/${id}`, data)
    return res.data
  },
}