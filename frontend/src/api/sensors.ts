import { api } from './client'

export interface SummaryBucket {
  bucket: string
  device_id: string
  metric: string
  avg_value: number
  min_value: number
  max_value: number
  sample_count: number
}

export const sensorsApi = {
  async summary(
    plotId: string,
    bucket: '1h' | '6h' = '1h',
    window: '1h' | '6h' | '24h' | '7d' | '30d' = '24h',
  ): Promise<SummaryBucket[]> {
    const { data } = await api.get<SummaryBucket[]>('/sensor/readings/summary', {
      params: { plot_id: plotId, bucket, window },
    })
    return data
  },
}