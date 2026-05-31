import client from '@/api/client'

export interface AdminUser {
  id: number
  username: string
  display_name: string
  role: string
  permissions: string[]
  is_active: boolean
}

export interface UserProfileData {
  user: AdminUser
  tags: UserProfileTag[]
  total_score: number
  tag_count: number
}

export interface UserProfileTag {
  dimension: string
  label: string
  score: number
  last_action: string | null
}

export const adminUsersApi = {
  list: (params?: {
    user_id?: number; username?: string; display_name?: string;
    is_active?: number; role?: string
  }) =>
    client.get<{ items: AdminUser[] }>('/admin/users', { params }),

  create: (data: { username: string; password: string; display_name?: string }) =>
    client.post<AdminUser>('/admin/users', data),

  update: (userId: number, data: { is_active?: boolean; display_name?: string }) =>
    client.patch<AdminUser>(`/admin/users/${userId}`, data),

  assignPermissions: (userId: number, permission_codes: string[]) =>
    client.post<{ granted: number; total: number }>(`/admin/users/${userId}/permissions`, { permission_codes }),

  profile: (userId: number) =>
    client.get<UserProfileData>(`/admin/users/${userId}/profile`),
}
