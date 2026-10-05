import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { tasksApi } from '../api/tasks'
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
    loading.value = true
    error.value = null
    try {
      tasks.value = await tasksApi.list()
    } catch (e: any) {
      error.value = e?.response?.data?.detail || 'Failed to load tasks'
      tasks.value = []
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