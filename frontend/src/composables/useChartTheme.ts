import { ref, onMounted, onUnmounted } from 'vue'

/**
 * Reactive, ECharts-friendly color values resolved from CSS variables.
 *
 * Why this exists:
 *   ECharts renders to canvas, where CSS `var(--x)` strings don't resolve.
 *   We read the computed values at runtime and re-read whenever the
 *   `data-theme` attribute on <html> changes.
 *
 * Our theme file stores colors as `R G B` triplets (for Tailwind's
 * opacity modifiers), so we convert them to `rgb(R, G, B)` strings.
 */
export function useChartTheme() {
  const text = ref('')
  const textMuted = ref('')
  const border = ref('')
  const card = ref('')

  function read() {
    const s = getComputedStyle(document.documentElement)
    text.value      = toRgb(s.getPropertyValue('--text'))
    textMuted.value = toRgb(s.getPropertyValue('--text-muted'))
    border.value    = toRgb(s.getPropertyValue('--border'))
    card.value      = toRgb(s.getPropertyValue('--card'))
  }

  let observer: MutationObserver | null = null

  onMounted(() => {
    read()
    observer = new MutationObserver(read)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
  })

  onUnmounted(() => {
    observer?.disconnect()
  })

  return { text, textMuted, border, card }
}

function toRgb(raw: string): string {
  const parts = raw.trim().split(/\s+/)
  if (parts.length === 3) {
    return `rgb(${parts[0]}, ${parts[1]}, ${parts[2]})`
  }
  return raw.trim()
}