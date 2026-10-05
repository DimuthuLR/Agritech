<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckCircle, Clock, XCircle, Activity, AlertTriangle,
  Droplets, Bug, Sprout,
} from 'lucide-vue-next'
import type { Task } from '../../types/task'

const props = defineProps<{ task: Task }>()
const emit = defineEmits<{ review: [task: Task] }>()

const TOOL_LABELS: Record<string, string> = {
  control_irrigation: 'Irrigation',
  schedule_fertigation: 'Fertigation',
  spray_chemical: 'Chemical spray',
}

const TOOL_ICONS: Record<string, any> = {
  control_irrigation: Droplets,
  schedule_fertigation: Sprout,
  spray_chemical: Bug,
}

const title = computed(() => TOOL_LABELS[props.task.tool] || props.task.tool)
const Icon = computed(() => TOOL_ICONS[props.task.tool] || AlertTriangle)
const isPending = computed(() => props.task.status === 'pending_approval')

function statusIcon(s: string) {
  switch (s) {
    case 'done': return CheckCircle
    case 'pending_approval': return Clock
    case 'rejected':
    case 'failed': return XCircle
    default: return Activity
  }
}

function statusPill(s: string) {
  switch (s) {
    case 'done': return 'bg-success/10 text-success'
    case 'pending_approval': return 'bg-warning/10 text-warning'
    case 'rejected':
    case 'failed': return 'bg-danger/10 text-danger'
    default: return 'bg-water/10 text-water'
  }
}

function formatArgs(args: Record<string, any>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
    .join(' · ')
}
</script>

<template>
  <div
    :class="['card transition-colors', isPending && 'border-warning/40']"
  >
    <div class="flex items-start gap-3">
      <div
        :class="[
          'w-9 h-9 rounded-sm shrink-0 flex items-center justify-center',
          isPending ? 'bg-warning/10 text-warning' : 'bg-card-hover text-muted',
        ]"
      >
        <component :is="Icon" :size="18" :stroke-width="1.75" />
      </div>

      <div class="flex-1 min-w-0">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="font-medium text-sm truncate">{{ title }}</h3>
            <p class="text-xs text-muted mt-0.5">
              {{ new Date(task.created_at).toLocaleString() }}
            </p>
          </div>

          <span :class="['pill text-xs shrink-0', statusPill(task.status)]">
            <component :is="statusIcon(task.status)" :size="11" :stroke-width="2" />
            {{ task.status.replace('_', ' ') }}
          </span>
        </div>

        <p class="text-xs text-muted mt-2 line-clamp-2">
          {{ task.reason }}
        </p>

        <p
          v-if="Object.keys(task.args).length"
          class="text-xs text-text mt-2 font-mono"
        >
          {{ formatArgs(task.args) }}
        </p>

        <div v-if="isPending" class="mt-3">
          <button
            class="btn-primary text-xs py-1.5 px-3"
            @click="emit('review', task)"
          >
            Review
          </button>
        </div>
      </div>
    </div>
  </div>
</template>