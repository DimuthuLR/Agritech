export interface Device {
  id: string
  tenant_id: string
  plot_id: string | null
  kind: 'sensor' | 'actuator' | 'gateway'
  model: string | null
  serial: string
  firmware: string | null
  is_active: boolean
  metadata: Record<string, unknown>
  last_seen_at: string | null
  created_at: string

  claimed_at: string | null
  hw_version: string | null
  chip_type: string | null

  uptime_sec: number | null
  free_heap_kb: number | null
  rssi_dbm: number | null
  battery_v: number | null

  last_error_code: string | null
  last_error_message: string | null
  last_error_at: string | null
}

export interface TestCommandResponse {
  device_id: string
  cmd_id: string
  action: string
  topic: string
}

export interface DeviceEvent {
  id: string
  event_type: string
  cmd_id: string | null
  action: string | null
  status: string | null
  error: string | null
  duration_ms: number | null
  occurred_at: string
  metadata: Record<string, unknown>
}