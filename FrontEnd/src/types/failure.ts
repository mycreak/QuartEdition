export interface TaskFailure {
  id: number
  task_id: number
  kind: string
  reason: string
  status: 'pending' | 'claimed' | 'resolved'
  claimed_by: number | null
  scope: 'batch' | 'item'
  item_title: string
  item_douban_id?: string
  retry_count: number
  claimed_at?: string | null
  resolved_at?: string | null
  created_at: string
}
