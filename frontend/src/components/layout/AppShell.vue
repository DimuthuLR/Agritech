<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import TopBar from './TopBar.vue'
import Sidebar from './Sidebar.vue'
import { useTasksStore } from '../../stores/tasks'
import { usePlotsStore } from '../../stores/plots'

const sidebarOpen = ref(false)
const route = useRoute()
const tasksStore = useTasksStore()
const plotsStore = usePlotsStore()

onMounted(async () => {
  await Promise.allSettled([
    tasksStore.fetchAll(),
    plotsStore.fetchAll(),
  ])
})
</script>

<template>
  <div class="min-h-screen bg-app-gradient flex flex-col">
    <TopBar @toggle-sidebar="sidebarOpen = !sidebarOpen" />

    <div class="flex flex-1 min-h-0">
      <Sidebar :open="sidebarOpen" @close="sidebarOpen = false" />

      <main class="flex-1 min-w-0 overflow-y-auto p-6 md:p-8 stagger-page">
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </Transition>
        </router-view>
      </main>
    </div>
  </div>
</template>