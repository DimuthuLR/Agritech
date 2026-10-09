<script setup lang="ts">
import { useTheme } from './composables/useTheme'
import ImpersonationBanner from './components/layout/ImpersonationBanner.vue'

// Initialise theme on app boot (applies data-theme attribute)
useTheme()
</script>

<template>
  <ImpersonationBanner />
  <router-view />
</template>