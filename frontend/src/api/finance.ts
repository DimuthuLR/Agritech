import { api } from './client'

export interface CostSummary {
  plot_id: string
  total_lkr: number
  breakdown: Record<string, number>
}

export interface PlotCost {
  plot_id: string
  name: string
  total_lkr: number
}

export interface TrendPoint {
  day: string
  total_lkr: number
}

export interface FinanceOverview {
  window_days: number
  total_lkr: number
  entry_count: number
  breakdown: Record<string, number>
  by_plot: PlotCost[]
  trend: TrendPoint[]
}

export interface LedgerEntry {
  id: string
  plot_id: string
  plot_name: string
  category: string
  qty: number
  unit: string
  amount_lkr: number
  occurred_at: string
}

export const financeApi = {
  async plotSummary(plotId: string): Promise<CostSummary> {
    const { data } = await api.get<CostSummary>('/finance/summary', {
      params: { plot_id: plotId },
    })
    return data
  },

  async overview(days: number = 30): Promise<FinanceOverview> {
    const { data } = await api.get<FinanceOverview>('/finance/overview', {
      params: { days },
    })
    return data
  },

  async ledger(limit: number = 50): Promise<LedgerEntry[]> {
    const { data } = await api.get<LedgerEntry[]>('/finance/ledger', {
      params: { limit },
    })
    return data
  },
}

// Human-readable labels + colors for categories
export const CATEGORY_META: Record<
  string,
  { label: string; color: string }
> = {
  water:      { label: 'Water',      color: '#38BDF8' },
  fertilizer: { label: 'Fertilizer', color: '#34D399' },
  chemical:   { label: 'Chemical',   color: '#F87171' },
  labor:      { label: 'Labor',      color: '#A78BFA' },
  energy:     { label: 'Energy',     color: '#FBBF24' },
  fuel:       { label: 'Fuel',       color: '#FB923C' },
  seed:       { label: 'Seed',       color: '#22D3EE' },
  equipment:  { label: 'Equipment',  color: '#94A3B8' },
  other:      { label: 'Other',      color: '#6B7280' },
}