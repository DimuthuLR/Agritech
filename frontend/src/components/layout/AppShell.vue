<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TopBar from './TopBar.vue'
import Sidebar from './Sidebar.vue'
import { useTasksStore } from '../../stores/tasks'
import { usePlotsStore } from '../../stores/plots'

const sidebarOpen = ref(false)
const tasksStore = useTasksStore()
const plotsStore = usePlotsStore()

onMounted(async () => {
  // Load shared data once at shell mount.
  // Both stores are cheap to re-fetch; running these in parallel.
  await Promise.allSettled([
    tasksStore.fetchAll(),
    plotsStore.fetchAll(),
  ])
})
</script>

<template>
  <div class="min-h-screen bg-bg text-text flex flex-col">
    <TopBar @toggle-sidebar="sidebarOpen = !sidebarOpen" />

    <div class="flex flex-1 overflow-hidden">
      <Sidebar :open="sidebarOpen" @close="sidebarOpen = false" />

      <main class="flex-1 overflow-y-auto p-4 md:p-6">
        <router-view />
      </main>
    </div>
  </div>
</template>