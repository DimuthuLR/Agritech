<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Leaf } from 'lucide-vue-next'
import { useDiagnosesStore } from '../stores/diagnoses'
import { usePlotsStore } from '../stores/plots'
import DiagnosisUploader from '../components/diagnosis/DiagnosisUploader.vue'
import DiagnosisResult from '../components/diagnosis/DiagnosisResult.vue'
import type { Diagnosis } from '../api/diagnoses'

const diagStore = useDiagnosesStore()
const plotsStore = usePlotsStore()
const selected = ref<Diagnosis | null>(null)

onMounted(async () => {
  // Ensure plots are loaded for the plot selector
  if (plotsStore.plots.length === 0) {
    await plotsStore.fetchAll()
  }
  await diagStore.fetchAll()
})

const sortedDiagnoses = computed(() =>
  diagStore.items
    .filter((d) => d.status === 'complete')
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    ),
)

function onComplete(diag: Diagnosis) {
  selected.value = diag
}
</script>

<template>
  <div class="max-w-5xl mx-auto space-y-6">

    <div>
      <h1 class="text-2xl font-semibold">Diagnosis</h1>
      <p class="text-muted text-sm mt-1">
        Photograph a leaf and get a teacher-mode diagnosis.
      </p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

      <!-- Left column: uploader + recent list -->
      <div class="space-y-6">
        <DiagnosisUploader @complete="onComplete" />

        <div v-if="diagStore.loading && diagStore.items.length === 0" class="card text-sm text-muted">
          Loading past diagnoses…
        </div>

        <div v-else-if="sortedDiagnoses.length > 0">
          <h2 class="text-sm font-medium mb-3 text-muted uppercase tracking-wide">
            Recent
          </h2>
          <div class="space-y-2">
            <button
              v-for="d in sortedDiagnoses"
              :key="d.id"
              :class="[
                'w-full text-left card hover:bg-card-hover transition-colors',
                selected?.id === d.id && 'border-accent',
              ]"
              @click="selected = d"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <div class="font-medium text-sm truncate">
                    {{ d.disease || 'Unknown' }}
                  </div>
                  <div class="text-xs text-muted mt-0.5">
                    {{ d.severity || '—' }} · {{ new Date(d.created_at).toLocaleString() }}
                  </div>
                </div>
                <span
                  v-if="d.requires_chemical"
                  class="pill-warning text-[10px] shrink-0"
                >
                  chemical
                </span>
              </div>
            </button>
          </div>
        </div>

        <div
          v-else-if="!diagStore.loading"
          class="card text-center py-8"
        >
          <Leaf :size="28" :stroke-width="1.5" class="text-muted mx-auto" />
          <p class="text-sm text-muted mt-3">No diagnoses yet.</p>
        </div>
      </div>

      <!-- Right column: selected result -->
      <div>
        <DiagnosisResult
          v-if="selected"
          :diagnosis="selected"
        />
        <div
          v-else
          class="card flex flex-col items-center justify-center py-16 text-center"
        >
          <Leaf :size="32" :stroke-width="1.5" class="text-muted" />
          <h3 class="font-medium mt-4">No diagnosis selected</h3>
          <p class="text-sm text-muted mt-1 max-w-xs">
            Upload a leaf photo or tap a past diagnosis to see the full report.
          </p>
        </div>
      </div>

    </div>
  </div>
</template>