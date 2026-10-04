<script setup lang="ts">
import { Sun, Moon, Monitor } from 'lucide-vue-next'
import { useTheme, type ThemeMode } from '../../composables/useTheme'

const theme = useTheme()

const options: { mode: ThemeMode; label: string; icon: any }[] = [
  { mode: 'light',  label: 'Light',  icon: Sun },
  { mode: 'dark',   label: 'Dark',   icon: Moon },
  { mode: 'system', label: 'System', icon: Monitor },
]
</script>

<template>
  <div class="flex items-center rounded-sm border border-border overflow-hidden">
    <button
      v-for="opt in options"
      :key="opt.mode"
      :title="opt.label"
      :aria-label="opt.label"
      :class="[
        'px-2 py-1.5 transition-colors',
        theme.mode.value === opt.mode
          ? 'bg-accent text-invert'
          : 'text-muted hover:text-text hover:bg-card-hover',
      ]"
      @click="theme.setMode(opt.mode)"
    >
      <component :is="opt.icon" :size="16" :stroke-width="1.75" />
    </button>
  </div>
</template>