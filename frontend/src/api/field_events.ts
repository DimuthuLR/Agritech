import { api } from './client'

export interface FieldEvent {
  id: string
  tenant_id: string
  plot_id: string
  event_type: 'override' | 'outcome' | 'observation'
  action_taken: string | null
  reported_by: string
  weather_forecast_mm: number | null
  weather_actual_mm: number | null
  forecast_window_hours: number | null
  reason: string | null
  outcome: 'worked' | 'failed' | 'unknown' | null
  details: Record<string, any>
  occurred_at: string
  verified_at: string | null
  created_at: string
}

export interface CreateOverrideInput {
  plot_id: string
  action_taken: string
  reason: string
  forecast_mm?: number | null
  forecast_window_hours?: number
}

export const fieldEventsApi = {
  async list(plotId?: string, days: number = 90): Promise<FieldEvent[]> {
    const params: Record<string, any> = { days }
    if (plotId) params.plot_id = plotId
    const { data } = await api.get<FieldEvent[]>('/field-events', { params })
    return data
  },

  async recordOverride(input: CreateOverrideInput): Promise<FieldEvent> {
    const { data } = await api.post<FieldEvent>('/field-events/override', input)
    return data
  },
}