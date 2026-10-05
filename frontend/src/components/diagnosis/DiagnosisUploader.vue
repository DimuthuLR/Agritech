<script setup lang="ts">
import { ref, computed } from 'vue'
import { Camera, X, Loader2 } from 'lucide-vue-next'
import { usePlotsStore } from '../../stores/plots'
import { useDiagnosesStore } from '../../stores/diagnoses'
import type { Diagnosis } from '../../api/diagnoses'

const emit = defineEmits<{ complete: [Diagnosis] }>()

const plotsStore = usePlotsStore()
const diagStore = useDiagnosesStore()

const fileInput = ref<HTMLInputElement | null>(null)
const previewUrl = ref<string | null>(null)
const selectedFile = ref<File | null>(null)
const selectedPlotId = ref<string>('')
const notes = ref('')
const error = ref<string | null>(null)

const hasPlots = computed(() => plotsStore.plots.length > 0)

function openPicker() {
  fileInput.value?.click()
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  // Validate size (10 MB)
  if (file.size > 10 * 1024 * 1024) {
    error.value = 'Image must be under 10 MB'
    return
  }
  if (!file.type.startsWith('image/')) {
    error.value = 'Please select an image file'
    return
  }

  error.value = null
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)

  // Preselect the first plot if none chosen
  if (!selectedPlotId.value && plotsStore.plots.length > 0) {
    selectedPlotId.value = plotsStore.plots[0].id
  }
}

function clearSelection() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = null
  selectedFile.value = null
  notes.value = ''
  error.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function upload() {
  if (!selectedFile.value || !selectedPlotId.value) return

  error.value = null
  const result = await diagStore.upload(
    selectedPlotId.value,
    selectedFile.value,
    notes.value.trim() || undefined,
  )

  if (result) {
    emit('complete', result)
    clearSelection()
  } else {
    error.value = diagStore.error || 'Diagnosis failed'
  }
}
</script>

<template>
  <div class="card">
    <input
      ref="fileInput"
      type="file"
      accept="image/*"
      capture="environment"
      class="hidden"
      @change="onFileSelected"
    />

    <!-- No image selected — show picker -->
    <div v-if="!previewUrl" class="text-center py-8">
      <button
        class="w-16 h-16 mx-auto rounded-full bg-accent-soft text-accent
               flex items-center justify-center hover:scale-105
               transition-transform"
        :disabled="!hasPlots"
        @click="openPicker"
      >
        <Camera :size="28" :stroke-width="1.75" />
      </button>

      <h3 class="font-medium mt-4">
        {{ hasPlots ? 'Snap a leaf photo' : 'Create a plot first' }}
      </h3>
      <p class="text-sm text-muted mt-1 max-w-xs mx-auto">
        <template v-if="hasPlots">
          Point at a leaf with visible symptoms and take a clear photo.
        </template>
        <template v-else>
          You need at least one plot before you can diagnose.
        </template>
      </p>
    </div>

    <!-- Image selected — show preview + form -->
    <div v-else class="space-y-4">
      <div class="relative rounded-sm overflow-hidden bg-card-hover">
        <img
          :src="previewUrl"
          alt="Leaf preview"
          class="w-full h-48 object-cover"
        />
        <button
          class="absolute top-2 right-2 w-8 h-8 rounded-full
                 bg-black/60 text-white flex items-center justify-center
                 hover:bg-black/80"
          @click="clearSelection"
        >
          <X :size="16" :stroke-width="2" />
        </button>
      </div>

      <div>
        <label class="block text-xs text-muted uppercase tracking-wide mb-1">
          Plot
        </label>
        <select v-model="selectedPlotId" class="input">
          <option v-for="p in plotsStore.plots" :key="p.id" :value="p.id">
            {{ p.name }}<template v-if="p.crop"> · {{ p.crop }}</template>
          </option>
        </select>
      </div>

      <div>
        <label class="block text-xs text-muted uppercase tracking-wide mb-1">
          Notes (optional)
        </label>
        <textarea
          v-model="notes"
          rows="2"
          class="input resize-none"
          placeholder="e.g. Leaves yellowing for 3 days"
        />
      </div>

      <div v-if="error" class="text-sm text-danger bg-danger/10 rounded-sm px-3 py-2">
        {{ error }}
      </div>

      <button
        class="btn-primary w-full"
        :disabled="diagStore.uploading"
        @click="upload"
      >
        <Loader2
          v-if="diagStore.uploading"
          :size="16"
          :stroke-width="2"
          class="animate-spin"
        />
        <Camera v-else :size="16" :stroke-width="2" />
        {{ diagStore.uploading ? 'Analyzing…' : 'Diagnose' }}
      </button>

      <p v-if="diagStore.uploading" class="text-xs text-muted text-center">
        This usually takes 5–10 seconds.
      </p>
    </div>
  </div>
</template>