import client from '@/api/client'
import type { TaskSubmit, TaskSubmitResponse } from '@/types/task'

export const adminTasksApi = {
  submit: (data: TaskSubmit) => client.post<TaskSubmitResponse>('/admin/tasks', data),

  list: (params: { type_num?: number; interval_id?: string; page?: number; page_size?: number }) =>
    client.get<{ items: Array<Record<string, unknown>>; page: number; page_size: number; total: number }>('/admin/tasks', { params }),
}

export interface TaskHistory {
  id: string
  admin_id: number
  task_type: string
  task_category?: 'api' | 'browser'
  parent_task_id?: string | null
  task_params: Record<string, unknown>
  status: 'submitted' | 'running' | 'done' | 'failed'
  message?: string | null
  elapsed_ms?: number | null
  created_at: string
  updated_at: string
}

export interface TaskHistoryDetail extends TaskHistory {
  related_failure?: {
    failure_id: number
    reason: string
    status: string
    retry_count: number
  } | null
}

export const adminTaskHistoryApi = {
  list: (params: {
    admin_id?: number; task_type?: string; status?: string; keyword?: string;
    since?: string; until?: string; page?: number; page_size?: number
  }) =>
    client.get<{ items: TaskHistory[]; total: number; page: number; page_size: number }>('/admin/task-history', { params }),

  detail: (id: string) => client.get<TaskHistoryDetail>(`/admin/task-history/${id}`),
}
