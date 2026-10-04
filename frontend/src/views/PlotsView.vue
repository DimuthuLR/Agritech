<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { Plus, Sprout } from 'lucide-vue-next'
import { usePlotsStore } from '../stores/plots'
import PlotCard from '../components/plots/PlotCard.vue'
import CreatePlotModal from '../components/plots/CreatePlotModal.vue'

const store = usePlotsStore()
const showCreate = ref(false)

onMounted(() => {
  store.fetchAll()
})

const totalArea = computed(() => store.totalAreaHa.toFixed(2))
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- Header -->
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold">Plots</h1>
        <p class="text-muted text-sm mt-1">
          <template v-if="store.count">
            {{ store.count }} plot{{ store.count === 1 ? '' : 's' }} ·
            {{ totalArea }} ha total
          </template>
          <template v-else>Your growing areas</template>
        </p>
      </div>

      <button class="btn-primary" @click="showCreate = true">
        <Plus :size="16" :stroke-width="2" />
        New plot
      </button>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="card text-muted text-sm">
      Loading plots…
    </div>

    <!-- Error -->
    <div
      v-else-if="store.error"
      class="card border-danger/40 text-danger text-sm"
    >
      {{ store.error }}
    </div>

    <!-- Empty state -->
    <div
      v-else-if="store.count === 0"
      class="card flex flex-col items-center gap-4 py-12 text-center"
    >
      <div class="w-12 h-12 rounded-full bg-accent-soft text-accent
                  flex items-center justify-center">
        <Sprout :size="24" :stroke-width="1.75" />
      </div>
      <div>
        <h3 class="font-medium">No plots yet</h3>
        <p class="text-sm text-muted mt-1">
          Create your first plot to start monitoring.
        </p>
      </div>
      <button class="btn-primary" @click="showCreate = true">
        <Plus :size="16" :stroke-width="2" />
        Create your first plot
      </button>
    </div>

    <!-- Grid of plots -->
    <div
      v-else
      class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <PlotCard v-for="p in store.plots" :key="p.id" :plot="p" />
    </div>

    <!-- Create modal -->
    <CreatePlotModal
      :open="showCreate"
      @close="showCreate = false"
      @created="showCreate = false"
    />
  </div>
</template>