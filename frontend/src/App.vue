<script setup lang="ts">
import { useTheme } from './composables/useTheme'

// Initialise theme on app boot (applies data-theme attribute)
useTheme()
</script>

<template>
  <router-view />
</template>