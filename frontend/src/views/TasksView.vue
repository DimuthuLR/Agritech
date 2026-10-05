<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ClipboardList } from 'lucide-vue-next'
import { useTasksStore } from '../stores/tasks'
import TaskCard from '../components/tasks/TaskCard.vue'
import TaskApprovalModal from '../components/tasks/TaskApprovalModal.vue'
import type { Task } from '../types/task'

type Filter = 'pending' | 'all' | 'done' | 'rejected'

const store = useTasksStore()
const filter = ref<Filter>('pending')
const selectedTask = ref<Task | null>(null)

const filters: { key: Filter; label: string }[] = [
  { key: 'pending', label: 'Pending' },
  { key: 'all', label: 'All' },
  { key: 'done', label: 'Done' },
  { key: 'rejected', label: 'Rejected' },
]

const filteredTasks = computed(() => {
  const t = store.tasks
  if (filter.value === 'all') return t
  if (filter.value === 'pending') {
    return t.filter((x) => x.status === 'pending_approval')
  }
  if (filter.value === 'done') {
    return t.filter((x) => x.status === 'done')
  }
  return t.filter((x) => x.status === 'rejected' || x.status === 'failed')
})

const counts = computed(() => ({
  pending: store.tasks.filter((t) => t.status === 'pending_approval').length,
  all: store.tasks.length,
  done: store.tasks.filter((t) => t.status === 'done').length,
  rejected: store.tasks.filter(
    (t) => t.status === 'rejected' || t.status === 'failed'
  ).length,
}))

onMounted(() => {
  store.fetchAll()
})

function review(task: Task) {
  selectedTask.value = task
}

function closeModal() {
  selectedTask.value = null
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">

    <div>
      <h1 class="text-2xl font-semibold">Tasks</h1>
      <p class="text-muted text-sm mt-1">
        <template v-if="counts.all">
          {{ counts.pending }} pending · {{ counts.all }} total
        </template>
        <template v-else>Work items for your farm</template>
      </p>
    </div>

    <div class="flex gap-1 border-b border-border">
      <button
        v-for="f in filters"
        :key="f.key"
        :class="[
          'px-3 py-2 text-sm font-medium transition-colors relative',
          filter === f.key ? 'text-accent' : 'text-muted hover:text-text',
        ]"
        @click="filter = f.key"
      >
        {{ f.label }}
        <span v-if="counts[f.key]" class="ml-1.5 text-xs text-muted">
          {{ counts[f.key] }}
        </span>
        <span
          v-if="filter === f.key"
          class="absolute bottom-0 left-0 right-0 h-0.5 bg-accent"
        />
      </button>
    </div>

    <div v-if="store.loading" class="text-muted text-sm">Loading tasks…</div>

    <div
      v-else-if="filteredTasks.length === 0"
      class="card flex flex-col items-center gap-3 py-12 text-center"
    >
      <div
        class="w-12 h-12 rounded-full bg-accent-soft text-accent
               flex items-center justify-center"
      >
        <ClipboardList :size="24" :stroke-width="1.75" />
      </div>
      <div>
        <h3 class="font-medium">No tasks here</h3>
        <p class="text-sm text-muted mt-1">
          <template v-if="filter === 'pending'">
            No tasks waiting for your approval.
          </template>
          <template v-else>Nothing to show in this filter.</template>
        </p>
      </div>
    </div>

    <div v-else class="grid grid-cols-1 gap-3">
      <TaskCard
        v-for="t in filteredTasks"
        :key="t.id"
        :task="t"
        @review="review"
      />
    </div>

    <TaskApprovalModal :task="selectedTask" @close="closeModal" />
  </div>
</template>