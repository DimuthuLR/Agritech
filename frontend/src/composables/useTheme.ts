import { ref, watchEffect } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'theme_mode'

const mode = ref<ThemeMode>(
  (localStorage.getItem(STORAGE_KEY) as ThemeMode) || 'system',
)

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolvedTheme(): 'light' | 'dark' {
  if (mode.value === 'system') {
    return systemPrefersDark() ? 'dark' : 'light'
  }
  return mode.value
}

function apply() {
  const theme = resolvedTheme()
  document.documentElement.setAttribute('data-theme', theme)
}

// Watch mode changes → apply
watchEffect(() => {
  localStorage.setItem(STORAGE_KEY, mode.value)
  apply()
})

// Watch system preference changes when in system mode
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (mode.value === 'system') apply()
})

export function useTheme() {
  return {
    mode,
    setMode(next: ThemeMode) { mode.value = next },
    current: resolvedTheme,
  }
}