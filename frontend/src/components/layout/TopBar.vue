<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import ThemeToggle from './ThemeToggle.vue'

import { Menu } from 'lucide-vue-next'

const emit = defineEmits<{ 'toggle-sidebar': [] }>()
const auth = useAuthStore()
const router = useRouter()

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <header class="h-16 border-b border-border bg-card flex items-center px-4 gap-4">
    <!-- Hamburger for mobile -->
    <button
      class="md:hidden text-muted hover:text-text"
      @click="emit('toggle-sidebar')"
      aria-label="Toggle menu"
    >
      <Menu :size="20" :stroke-width="1.75" />
    </button>

    <!-- Logo / brand -->
    <router-link to="/dashboard" class="flex items-center gap-2 font-semibold">
      <span class="w-6 h-6 rounded-sm bg-accent"></span>
      <span>AgriTech</span>
    </router-link>

    <div class="flex-1"></div>

    <!-- Theme toggle -->
    <ThemeToggle />

    <!-- User menu -->
    <div class="relative group">
      <button class="flex items-center gap-2 text-sm">
        <span class="w-8 h-8 rounded-full bg-accent-soft text-accent
                     flex items-center justify-center font-medium">
          {{ auth.user?.email?.[0]?.toUpperCase() || '?' }}
        </span>
        <span class="hidden md:inline text-muted">
          {{ auth.user?.email }}
        </span>
      </button>

      <!-- Dropdown -->
      <div class="absolute right-0 top-full mt-2 w-48 card hidden
                  group-hover:block z-50 p-1">
        <button
          class="w-full text-left px-3 py-2 rounded-sm text-sm
                 hover:bg-card-hover"
          @click="logout"
        >
          Log out
        </button>
      </div>
    </div>
  </header>
</template>