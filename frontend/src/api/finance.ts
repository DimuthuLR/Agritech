import { api } from './client'

export interface CostSummary {
  plot_id: string
  total_lkr: number
  breakdown: Record<string, number>
}

export const financeApi = {
  async plotSummary(plotId: string): Promise<CostSummary> {
    const { data } = await api.get<CostSummary>('/finance/summary', {
      params: { plot_id: plotId },
    })
    return data
  },
}