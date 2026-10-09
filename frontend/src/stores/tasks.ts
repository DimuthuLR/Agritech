import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { tasksApi } from '../api/tasks'
import { useAuthStore } from './auth'
import type { Task } from '../types/task'

export const useTasksStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const pending = computed(() =>
    tasks.value.filter((t) => t.status === 'pending_approval')
  )
  const pendingCount = computed(() => pending.value.length)

  async function fetchAll(): Promise<void> {
    const auth = useAuthStore()
    // Platform users have no tenant — skip the tenant-scoped fetch entirely.
    // Also skip if there's no authenticated user yet (first render before
    // the auth store hydrates from localStorage).
    if (!auth.user?.tenant_id) {
      tasks.value = []
      return
    }

    loading.value = true
    error.value = null
    try {
      tasks.value = await tasksApi.list()
    } catch (e: any) {
      // A suspended tenant gets 403 here — treat it as "no tasks" rather
      // than surfacing a scary error in the UI. The dashboard will show
      // the suspended banner separately.
      if (e?.response?.status === 403) {
        tasks.value = []
      } else {
        error.value = e?.response?.data?.detail || 'Failed to load tasks'
        tasks.value = []
      }
    } finally {
      loading.value = false
    }
  }

  async function approve(id: string): Promise<Task> {
    const updated = await tasksApi.approve(id)
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx >= 0) tasks.value[idx] = updated
    return updated
  }

  async function reject(id: string, reason: string): Promise<Task> {
    const updated = await tasksApi.reject(id, reason)
    const idx = tasks.value.findIndex((t) => t.id === id)
    if (idx >= 0) tasks.value[idx] = updated
    return updated
  }

  return {
    tasks, loading, error,
    pending, pendingCount,
    fetchAll, approve, reject,
  }
})