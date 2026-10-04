import { api } from './client'
import type { Task } from '../types/task'

export const tasksApi = {
  async list(plotId?: string): Promise<Task[]> {
    const params = plotId ? { plot_id: plotId } : {}
    const { data } = await api.get<Task[]>('/tasks', { params })
    return data
  },

  async approve(id: string): Promise<Task> {
    const { data } = await api.post<Task>(`/tasks/${id}/approve`)
    return data
  },

  async reject(id: string, reason: string): Promise<Task> {
    const { data } = await api.post<Task>(`/tasks/${id}/reject`, { reason })
    return data
  },
}