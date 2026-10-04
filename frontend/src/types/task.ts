export interface Task {
  id: string
  tenant_id: string
  plot_id: string
  device_id: string | null
  tool: string
  args: Record<string, any>
  reason: string
  status: string
  requires_approval: boolean
  idempotency_key: string
  created_by: string | null
  created_at: string
  approved_at: string | null
  dispatched_at: string | null
  acked_at: string | null
  completed_at: string | null
  result: Record<string, any> | null
}