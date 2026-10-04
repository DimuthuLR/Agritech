<script setup lang="ts">
import { ref } from 'vue'
import TopBar from './TopBar.vue'
import Sidebar from './Sidebar.vue'

const sidebarOpen = ref(false)
</script>

<template>
  <div class="min-h-screen bg-bg text-text flex flex-col">

    <!-- Top bar — always visible -->
    <TopBar @toggle-sidebar="sidebarOpen = !sidebarOpen" />

    <div class="flex flex-1 overflow-hidden">

      <!-- Sidebar — slides in on mobile -->
      <Sidebar :open="sidebarOpen" @close="sidebarOpen = false" />

      <!-- Main content -->
      <main class="flex-1 overflow-y-auto p-4 md:p-6">
        <router-view />
      </main>

    </div>
  </div>
</template>