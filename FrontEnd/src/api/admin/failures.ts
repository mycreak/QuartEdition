import client from '@/api/client'
import type { TaskFailure } from '@/types/failure'

export const adminFailuresApi = {
  list: (params: { status?: string; page?: number; page_size?: number }) =>
    client.get<{ items: TaskFailure[]; total: number; page: number; page_size: number }>('/admin/failures', { params }),

  detail: (id: number) => client.get<TaskFailure>(`/admin/failures/${id}`),

  claim: (id: number) => client.post<{ success: boolean; message: string }>(`/admin/failures/${id}/claim`),

  release: (id: number) => client.post<{ success: boolean; message: string }>(`/admin/failures/${id}/release`),

  resolve: (id: number) => client.post<{ success: boolean; message: string }>(`/admin/failures/${id}/resolve`),
}
