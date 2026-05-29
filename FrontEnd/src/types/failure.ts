export interface TaskFailure {
  id: number
  task_id: number
  /** 来自 task_history LEFT JOIN，任务提交者 ID */
  admin_id?: number
  /** 来自 task_history LEFT JOIN，任务类型 */
  task_type?: string
  /** 来自 task_history LEFT JOIN，原始任务参数 */
  task_params?: Record<string, unknown>
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
