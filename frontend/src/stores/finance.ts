import { defineStore } from 'pinia'
import { ref } from 'vue'
import { financeApi, type FinanceOverview, type LedgerEntry } from '../api/finance'

export const useFinanceStore = defineStore('finance', () => {
  const overview = ref<FinanceOverview | null>(null)
  const ledger = ref<LedgerEntry[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const days = ref(30)

  async function fetchOverview(newDays?: number): Promise<void> {
    if (newDays !== undefined) days.value = newDays
    loading.value = true
    error.value = null
    try {
      overview.value = await financeApi.overview(days.value)
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Failed to load overview'
      overview.value = null
    } finally {
      loading.value = false
    }
  }

  async function fetchLedger(limit: number = 50): Promise<void> {
    try {
      ledger.value = await financeApi.ledger(limit)
    } catch (e: any) {
      // Silent — the ledger is secondary
    }
  }

  return { overview, ledger, loading, error, days, fetchOverview, fetchLedger }
})