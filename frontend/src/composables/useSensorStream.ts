import { ref, onUnmounted } from 'vue'

export interface SensorReading {
  time: string
  device_id: string
  metric: string
  value: number
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'
const WS_BASE = API_BASE.replace(/^http/, 'ws')

// Ring buffer capacity per metric
const CAP = 500

export function useSensorStream(plotId: string) {
  const connected = ref(false)
  const error = ref<string | null>(null)

  // Store readings per metric as arrays of { time, value }
  const series = ref<Record<string, { time: string; value: number }[]>>({})

  let ws: WebSocket | null = null

  function push(metric: string, reading: SensorReading) {
    const arr = series.value[metric] ?? []
    arr.push({ time: reading.time, value: reading.value })
    // Trim to ring buffer size
    if (arr.length > CAP) {
      arr.splice(0, arr.length - CAP)
    }
    series.value[metric] = arr
  }

  function seed(
    metric: string,
    points: { time: string; value: number }[],
  ) {
    if (points.length === 0) return

    const existing = series.value[metric] ?? []
    const seen = new Set(existing.map((p) => p.time))

    // Merge existing (live) with historical, dedupe by exact time,
    // then sort ascending so the chart renders left-to-right.
    const merged = [
      ...existing,
      ...points.filter((p) => !seen.has(p.time)),
    ].sort(
      (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime(),
    )

    series.value[metric] = merged.slice(-CAP)
  }

  function connect() {
    const token = localStorage.getItem('access_token')
    if (!token) {
      error.value = 'No auth token'
      return
    }

    // Some browsers/backends require the token as a query param for WS
    // (can't set Authorization headers on WebSocket)
    const url = `${WS_BASE}/sensor/ws/${plotId}?token=${token}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      error.value = null
    }

    ws.onmessage = (evt) => {
      try {
        const reading = JSON.parse(evt.data) as SensorReading
        push(reading.metric, reading)
      } catch (e) {
        // Ignore malformed frames
      }
    }

    ws.onerror = () => {
      error.value = 'WebSocket error'
    }

    ws.onclose = () => {
      connected.value = false
    }
  }

  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  onUnmounted(disconnect)

  return { connected, error, series, connect, disconnect, seed }
}