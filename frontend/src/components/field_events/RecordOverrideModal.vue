<script setup lang="ts">
import { ref, watch } from 'vue'
import { X, ClipboardList } from 'lucide-vue-next'
import { fieldEventsApi, type FieldEvent } from '../../api/field_events'

const props = defineProps<{
  open: boolean
  plotId: string
}>()

const emit = defineEmits<{
  close: []
  created: [FieldEvent]
}>()

const TOOL_OPTIONS = [
  { value: 'control_irrigation', label: 'Irrigation' },
  { value: 'schedule_fertigation', label: 'Fertigation' },
  { value: 'spray_chemical', label: 'Chemical spray' },
  { value: 'other', label: 'Something else' },
]

const actionTaken = ref('spray_chemical')
const reason = ref('')
const forecastMm = ref<number | null>(null)
const windowHours = ref(6)
const submitting = ref(false)
const error = ref<string | null>(null)

// Reset form when modal opens
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      actionTaken.value = 'spray_chemical'
      reason.value = ''
      forecastMm.value = null
      windowHours.value = 6
      error.value = null
    }
  },
)

async function submit() {
  if (!reason.value.trim()) {
    error.value = 'Please explain why you took this action'
    return
  }
  submitting.value = true
  error.value = null

  try {
    const event = await fieldEventsApi.recordOverride({
      plot_id: props.plotId,
      action_taken: actionTaken.value,
      reason: reason.value.trim(),
      forecast_mm: forecastMm.value,
      forecast_window_hours: windowHours.value,
    })
    emit('created', event)
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to record action'
  } finally {
    submitting.value = false
  }
}

function close() {
  if (submitting.value) return
  emit('close')
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center p-4
           bg-black/50 backdrop-blur-sm"
    @click.self="close"
  >
    <div class="card w-full max-w-lg max-h-[90vh] overflow-y-auto">

      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-2">
          <ClipboardList :size="18" :stroke-width="1.75" class="text-accent" />
          <h2 class="text-lg font-semibold">Record an action</h2>
        </div>
        <button
          class="text-muted hover:text-text"
          @click="close"
          aria-label="Close"
        >
          <X :size="18" :stroke-width="1.75" />
        </button>
      </div>

      <p class="text-sm text-muted mb-5">
        Log something you did that went against the platform's advice.
        The AI will learn from the outcome and adjust its future reasoning.
      </p>

      <form @submit.prevent="submit" class="space-y-4">

        <div>
          <label class="block text-xs text-muted uppercase tracking-wide mb-1">
            What did you do?
          </label>
          <select v-model="actionTaken" class="input" required>
            <option v-for="t in TOOL_OPTIONS" :key="t.value" :value="t.value">
              {{ t.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-xs text-muted uppercase tracking-wide mb-1">
            Why? (required)
          </label>
          <textarea
            v-model="reason"
            rows="3"
            class="input resize-none"
            placeholder="e.g. The forecast said rain, but my plot rarely gets rain in October. I sprayed anyway."
            required
          />
        </div>

        <details class="text-sm">
          <summary class="cursor-pointer text-muted hover:text-text">
            Weather context (optional)
          </summary>
          <div class="grid grid-cols-2 gap-3 mt-3">
            <div>
              <label class="block text-xs text-muted uppercase tracking-wide mb-1">
                Forecast (mm)
              </label>
              <input
                v-model.number="forecastMm"
                type="number"
                step="0.1"
                min="0"
                class="input"
                placeholder="15"
              />
            </div>
            <div>
              <label class="block text-xs text-muted uppercase tracking-wide mb-1">
                Window (hours)
              </label>
              <input
                v-model.number="windowHours"
                type="number"
                step="1"
                min="1"
                max="48"
                class="input"
              />
            </div>
          </div>
          <p class="text-xs text-muted mt-2">
            If provided, we'll check what actually happened 24 hours later and
            log the outcome automatically.
          </p>
        </details>

        <div
          v-if="error"
          class="text-sm text-danger bg-danger/10 rounded-sm px-3 py-2"
        >
          {{ error }}
        </div>

        <div class="flex gap-2 pt-2">
          <button type="button" class="btn-ghost flex-1" @click="close">
            Cancel
          </button>
          <button type="submit" class="btn-primary flex-1" :disabled="submitting">
            {{ submitting ? 'Recording…' : 'Record' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>