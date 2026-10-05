<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertTriangle, Bug, Info,
  ClipboardList, Wallet, Sparkles,
} from 'lucide-vue-next'
import type { Diagnosis } from '../../api/diagnoses'

const props = defineProps<{ diagnosis: Diagnosis }>()

const isComplete = computed(() => props.diagnosis.status === 'complete')
const isFailed = computed(() => props.diagnosis.status === 'failed')

const severityPill = computed(() => {
  switch (props.diagnosis.severity?.toLowerCase()) {
    case 'high': return 'pill-danger'
    case 'moderate': return 'pill-warning'
    case 'low': return 'pill-muted'
    default: return 'pill-muted'
  }
})

const cost = computed(() => {
  const d = props.diagnosis
  return d.calculated_cost_lkr ?? d.estimated_cost_lkr ?? null
})

const isCalculatedCost = computed(() => props.diagnosis.calculated_cost_lkr != null)
</script>

<template>
  <div class="card space-y-5">

    <!-- Failed state -->
    <div v-if="isFailed" class="text-center py-6">
      <AlertTriangle :size="32" class="text-danger mx-auto" :stroke-width="1.5" />
      <h3 class="font-medium mt-3">Diagnosis failed</h3>
      <p class="text-sm text-muted mt-1">
        {{ diagnosis.status === 'failed' ? 'The vision model could not process this image.' : '' }}
      </p>
    </div>

    <template v-else-if="isComplete">
      <!-- Header: disease + severity + confidence -->
      <div class="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 class="text-xl font-semibold">{{ diagnosis.disease || 'Unknown' }}</h2>
          <div class="flex items-center gap-2 mt-2">
            <span :class="severityPill">{{ diagnosis.severity || '—' }} severity</span>
            <span v-if="diagnosis.confidence" class="text-xs text-muted">
              {{ Math.round(diagnosis.confidence * 100) }}% confidence
            </span>
          </div>
        </div>

        <div class="text-right">
          <div class="flex items-center gap-1 text-muted text-xs uppercase tracking-wide justify-end">
            <Wallet :size="12" :stroke-width="2" />
            {{ isCalculatedCost ? 'Cost (calculated)' : 'Cost (estimate)' }}
          </div>
          <div class="text-lg font-semibold mt-1">
            LKR {{ cost ? cost.toFixed(0) : '—' }}
          </div>
        </div>
      </div>

      <!-- What's happening -->
      <div v-if="diagnosis.what_is_happening">
        <div class="flex items-center gap-2 text-xs uppercase tracking-wide text-muted mb-2">
          <Info :size="12" :stroke-width="2" />
          What's happening
        </div>
        <p class="text-sm leading-relaxed">{{ diagnosis.what_is_happening }}</p>
      </div>

      <!-- Treatment -->
      <div v-if="diagnosis.treatment_steps?.length">
        <div class="flex items-center gap-2 text-xs uppercase tracking-wide text-muted mb-2">
          <ClipboardList :size="12" :stroke-width="2" />
          What to do this week
        </div>
        <ul class="space-y-2">
          <li
            v-for="(step, i) in diagnosis.treatment_steps"
            :key="i"
            class="flex gap-3 text-sm leading-relaxed"
          >
            <span class="text-accent shrink-0 font-mono text-xs mt-0.5">
              {{ String(i + 1).padStart(2, '0') }}
            </span>
            <span>{{ step }}</span>
          </li>
        </ul>
      </div>

      <!-- Prevention -->
      <div v-if="diagnosis.prevention_next_season?.length">
        <div class="flex items-center gap-2 text-xs uppercase tracking-wide text-muted mb-2">
          <Sparkles :size="12" :stroke-width="2" />
          How to prevent next season
        </div>
        <ul class="space-y-2">
          <li
            v-for="(step, i) in diagnosis.prevention_next_season"
            :key="i"
            class="flex gap-3 text-sm leading-relaxed"
          >
            <span class="text-water shrink-0 font-mono text-xs mt-0.5">
              {{ String(i + 1).padStart(2, '0') }}
            </span>
            <span>{{ step }}</span>
          </li>
        </ul>
      </div>

      <!-- Chemical flag -->
      <div
        v-if="diagnosis.requires_chemical"
        class="rounded-sm border border-warning/30 bg-warning/5 p-3
               flex items-start gap-2"
      >
        <Bug :size="16" :stroke-width="1.75" class="text-warning shrink-0 mt-0.5" />
        <div class="text-sm">
          <p class="font-medium text-warning">Chemical treatment recommended</p>
          <p class="text-muted mt-1 text-xs leading-relaxed">
            A spray task has been created and is waiting for your approval.
            Check the <router-link to="/tasks" class="text-accent underline">Tasks</router-link> page.
          </p>
        </div>
      </div>

      <!-- Provenance -->
      <div class="pt-4 border-t border-border flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span>Model: {{ diagnosis.model || '—' }}</span>
        <span>Prompt: {{ diagnosis.prompt_version || '—' }}</span>
        <span>{{ new Date(diagnosis.created_at).toLocaleString() }}</span>
      </div>
    </template>
  </div>
</template>