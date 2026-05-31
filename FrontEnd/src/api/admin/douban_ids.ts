import client from '@/api/client'

export interface DoubanId {
  douban_id: string
  title: string
  source: string
  type_num: number | null
  interval_id: string | null
  admin_id: number | null
  claimed_by_name: string | null
  is_acquired: number
  is_scraped: number
  acquired_at: string | null
  task_id: number | null
  created_at: string
}

export const adminDoubanIdsApi = {
  list: (params: {
    keyword?: string; is_acquired?: string; type_num?: number;
    interval_id?: string; page?: number; page_size?: number
  }) =>
    client.get<{ items: DoubanId[]; total: number; page: number; page_size: number }>(
      '/admin/douban-ids', { params }
    ),

  add: (data: { douban_id: string; title: string; type_num?: number; interval_id?: string }) =>
    client.post<{ success: boolean; douban_id: string }>('/admin/douban-ids', data),

  acquire: (doubanId: string) =>
    client.post<{ success: boolean; douban_id: string }>(`/admin/douban-ids/${doubanId}/acquire`),

  release: (doubanId: string) =>
    client.post<{ success: boolean; douban_id: string; message: string }>(`/admin/douban-ids/${doubanId}/release`),

  delete: (doubanId: string) =>
    client.delete<{ success: boolean; douban_id: string; message: string }>(`/admin/douban-ids/${doubanId}`),
}
