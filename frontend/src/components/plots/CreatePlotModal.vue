<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X } from 'lucide-vue-next'
import { farmsApi, type Farm } from '../../api/farms'
import { usePlotsStore } from '../../stores/plots'
import {
  SOIL_TYPE_LABELS,
  GROWTH_STAGES,
  type SoilType,
  type CreatePlotInput,
} from '../../types/plot'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; created: [] }>()

const store = usePlotsStore()

const farms = ref<Farm[]>([])
const loadingFarms = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)

const form = ref<CreatePlotInput>({
  name: '',
  farm_id: '',
  area_ha: 0.1,
  crop: 'tomato',
  stage: 'seedling',
  soil_type: 'coco_peat' as SoilType,
})

const soilOptions = computed(() =>
  Object.entries(SOIL_TYPE_LABELS).map(([value, label]) => ({ value, label }))
)

// Load farms when modal opens
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    error.value = null
    loadingFarms.value = true
    try {
      farms.value = await farmsApi.list()
      if (farms.value.length && !form.value.farm_id) {
        form.value.farm_id = farms.value[0].id
      }
    } catch {
      error.value = 'Failed to load farms'
    } finally {
      loadingFarms.value = false
    }
  },
)

async function submit() {
  error.value = null
  submitting.value = true
  try {
    const created = await store.create(form.value)
    if (!created) {
      error.value = store.error || 'Failed to create plot'
      return
    }
    emit('created')
    // Reset form
    form.value = {
      name: '',
      farm_id: farms.value[0]?.id || '',
      area_ha: 0.1,
      crop: 'tomato',
      stage: 'seedling',
      soil_type: 'coco_peat' as SoilType,
    }
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
    <div class="card w-full max-w-md max-h-[90vh] overflow-y-auto">

      <!-- Header -->
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-lg font-semibold">New plot</h2>
        <button
          class="text-muted hover:text-text p-1 rounded-sm hover:bg-card-hover"
          @click="close"
        >
          <X :size="18" :stroke-width="1.75" />
        </button>
      </div>

      <!-- Form -->
      <form @submit.prevent="submit" class="space-y-4">

        <div>
          <label class="block text-sm text-muted mb-1">Farm</label>
          <select v-model="form.farm_id" class="input" :disabled="loadingFarms" required>
            <option v-if="loadingFarms" value="">Loading…</option>
            <option v-for="f in farms" :key="f.id" :value="f.id">{{ f.name }}</option>
          </select>
        </div>

        <div>
          <label class="block text-sm text-muted mb-1">Plot name</label>
          <input v-model="form.name" class="input" placeholder="Greenhouse 1" required />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm text-muted mb-1">Area (ha)</label>
            <input
              v-model.number="form.area_ha"
              type="number" step="0.01" min="0.01"
              class="input" required
            />
          </div>
          <div>
            <label class="block text-sm text-muted mb-1">Stage</label>
            <select v-model="form.stage" class="input">
              <option v-for="s in GROWTH_STAGES" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
        </div>

        <div>
          <label class="block text-sm text-muted mb-1">Crop</label>
          <input v-model="form.crop" class="input" placeholder="tomato" />
        </div>

        <div>
          <label class="block text-sm text-muted mb-1">Soil / Growing medium</label>
          <select v-model="form.soil_type" class="input" required>
            <option v-for="opt in soilOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>

        <div v-if="error" class="text-sm text-danger bg-danger/10 rounded-sm px-3 py-2">
          {{ error }}
        </div>

        <div class="flex gap-2 pt-2">
          <button type="button" class="btn-ghost flex-1" @click="close">
            Cancel
          </button>
          <button type="submit" class="btn-primary flex-1" :disabled="submitting">
            {{ submitting ? 'Creating…' : 'Create plot' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>