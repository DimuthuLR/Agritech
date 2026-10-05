<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X, CheckCircle, XCircle } from 'lucide-vue-next'
import type { Task } from '../../types/task'
import { useTasksStore } from '../../stores/tasks'

const props = defineProps<{ task: Task | null }>()
const emit = defineEmits<{ close: [] }>()

const store = useTasksStore()
const submitting = ref(false)
const showReject = ref(false)
const rejectReason = ref('')
const error = ref<string | null>(null)

const isPending = computed(() => props.task?.status === 'pending_approval')

const TOOL_LABELS: Record<string, string> = {
  control_irrigation: 'Irrigation',
  schedule_fertigation: 'Fertigation',
  spray_chemical: 'Chemical spray',
}

const title = computed(() =>
  props.task ? (TOOL_LABELS[props.task.tool] || props.task.tool) : ''
)

watch(() => props.task, () => {
  showReject.value = false
  rejectReason.value = ''
  error.value = null
})

async function approve() {
  if (!props.task) return
  submitting.value = true
  error.value = null
  try {
    await store.approve(props.task.id)
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Approval failed'
  } finally {
    submitting.value = false
  }
}

async function reject() {
  if (!props.task) return
  if (!rejectReason.value.trim()) {
    error.value = 'Please provide a reason'
    return
  }
  submitting.value = true
  error.value = null
  try {
    await store.reject(props.task.id, rejectReason.value.trim())
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Rejection failed'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div
    v-if="task"
    class="fixed inset-0 z-50 flex items-center justify-center p-4
           bg-black/50 backdrop-blur-sm"
    @click.self="emit('close')"
  >
    <div class="card w-full max-w-lg max-h-[90vh] overflow-y-auto">

      <div class="flex items-center justify-between mb-5">
        <h2 class="text-lg font-semibold">{{ title }}</h2>
        <button class="text-muted hover:text-text" @click="emit('close')">
          <X :size="18" :stroke-width="1.75" />
        </button>
      </div>

      <div class="mb-4">
        <div class="text-xs text-muted uppercase tracking-wide mb-1">Status</div>
        <div class="text-sm font-medium">{{ task.status.replace('_', ' ') }}</div>
      </div>

      <div class="mb-4">
        <div class="text-xs text-muted uppercase tracking-wide mb-1">Reason</div>
        <p class="text-sm">{{ task.reason }}</p>
      </div>

      <div v-if="Object.keys(task.args).length" class="mb-4">
        <div class="text-xs text-muted uppercase tracking-wide mb-1">Arguments</div>
        <div class="bg-card-hover rounded-sm p-3 font-mono text-xs space-y-1">
          <div v-for="(v, k) in task.args" :key="k" class="flex justify-between">
            <span class="text-muted">{{ k }}</span>
            <span>{{ v }}</span>
          </div>
        </div>
      </div>

      <div class="text-xs text-muted mb-4">
        Created {{ new Date(task.created_at).toLocaleString() }}
      </div>

      <div
        v-if="error"
        class="mb-4 text-sm text-danger bg-danger/10 rounded-sm px-3 py-2"
      >
        {{ error }}
      </div>

      <div v-if="showReject" class="mb-4">
        <label class="block text-xs text-muted uppercase tracking-wide mb-1">
          Reason for rejection (required)
        </label>
        <textarea
          v-model="rejectReason"
          rows="3"
          class="input resize-none"
          placeholder="Why are you rejecting this task?"
        />
      </div>

      <div v-if="isPending" class="flex gap-2">
        <template v-if="!showReject">
          <button
            class="btn-primary flex-1"
            :disabled="submitting"
            @click="approve"
          >
            <CheckCircle :size="16" :stroke-width="2" />
            {{ submitting ? 'Approving…' : 'Approve' }}
          </button>
          <button
            class="btn-ghost flex-1"
            :disabled="submitting"
            @click="showReject = true"
          >
            <XCircle :size="16" :stroke-width="2" />
            Reject
          </button>
        </template>
        <template v-else>
          <button
            class="btn-ghost flex-1"
            :disabled="submitting"
            @click="showReject = false"
          >
            Cancel
          </button>
          <button
            class="btn-danger flex-1"
            :disabled="submitting"
            @click="reject"
          >
            <XCircle :size="16" :stroke-width="2" />
            {{ submitting ? 'Rejecting…' : 'Confirm reject' }}
          </button>
        </template>
      </div>

      <div v-else class="text-xs text-muted text-center">
        This task is no longer pending.
      </div>

    </div>
  </div>
</template>