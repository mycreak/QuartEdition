import client from '@/api/client'

export interface AdminUser {
  id: number
  username: string
  display_name: string
  role: string
  permissions: string[]
  is_active: boolean
}

export const adminUsersApi = {
  list: () =>
    client.get<{ items: AdminUser[] }>('/admin/users'),

  create: (data: { username: string; password: string; display_name?: string }) =>
    client.post<AdminUser>('/admin/users', data),

  update: (userId: number, data: { is_active?: boolean; display_name?: string }) =>
    client.patch<AdminUser>(`/admin/users/${userId}`, data),

  assignPermissions: (userId: number, permission_codes: string[]) =>
    client.post<{ granted: number; total: number }>(`/admin/users/${userId}/permissions`, { permission_codes }),
}
