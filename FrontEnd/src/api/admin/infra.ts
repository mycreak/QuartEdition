import client from '@/api/client'

export interface ProxyItem {
  id: number
  host: string
  port: number
  region: string
  source: string
  is_alive: boolean
  success_rate: number
  avg_latency_ms: number
  has_auth: boolean
  remark: string
  proxy_type: 'http' | 'https' | 'socks5'
  enabled: boolean
  fail_count: number
  success_count: number
  last_used: string
  added_at: string
}

export interface ProxyStats {
  total: number
  alive: number
  dead: number
  banned: number
}

export interface CookieAccount {
  id: string
  label: string
  platform: string
  remark?: string
  allowed_regions: string[]
  dbcl2_preview: string
  saved_at: string
  state: 'active' | 'suspicious' | 'banned'
  enabled: boolean
  last_used_at: string
  fail_count: number
  success_count: number
  usage_count: number
  expired_at?: string
}

export interface CookieStats {
  total: number
  active: number
  suspicious: number
  banned: number
  by_region: Record<string, number>
}

export interface CookieStatusSummary {
  stats: CookieStats
  accounts: CookieAccount[]
  has_dbcl2: boolean
  cookie_valid: boolean
}

export interface ProxyOption {
  id: number
  key: string
  label: string
  has_auth: boolean
  region: string
}

export interface CookieOption {
  id: string
  label: string
  platform: string
  allowed_regions: string[]
}

export const adminProxyApi = {
  list: (params?: { status?: string; region?: string; keyword?: string; page?: number; page_size?: number }) =>
    client.get<{ items: ProxyItem[]; stats: ProxyStats; total: number; page: number; page_size: number }>('/admin/proxies', { params }),

  add: (data: { host: string; port: number; region?: string; remark?: string; proxy_type?: string; username?: string; password?: string; enabled?: boolean }) =>
    client.post<{ success: boolean; id: number; key: string }>('/admin/proxies', data),

  update: (id: number, data: { remark?: string; username?: string; password?: string; region?: string; enabled?: boolean; proxy_type?: string }) =>
    client.patch<{ success: boolean }>(`/admin/proxies/${id}`, data),

  remove: (id: number) =>
    client.delete<{ success: boolean; key: string }>(`/admin/proxies/${id}`),

  test: (data: { id: number } | { host: string; port: number }) =>
    client.post<{ success: boolean; latency_ms?: number; exit_ip?: string; message?: string }>(
      '/admin/proxies/test', data,
      { timeout: 90_000 },
    ),

  options: () =>
    client.get<{ items: ProxyOption[] }>('/admin/proxies/options'),

  healthCheck: () =>
    client.post<Record<string, unknown>>('/admin/proxies/health-check'),
}

export const adminCookieApi = {
  list: (params?: { status?: string; keyword?: string; page?: number; page_size?: number }) =>
    client.get<{ items: CookieAccount[]; stats: CookieStats; total: number; page: number; page_size: number }>('/admin/cookies', { params }),

  add: (data: {
    platform: string; dbcl2: string; allowed_regions: string[]; bid?: string; label?: string; remark?: string
  }) =>
    client.post<{ success: boolean; account_id: string }>('/admin/cookies', data),

  update: (id: string, data: { label?: string; remark?: string; platform?: string; enabled?: boolean; allowed_regions?: string[] }) =>
    client.patch<{ success: boolean }>(`/admin/cookies/${id}`, data),

  remove: (accountId: string) =>
    client.delete<{ success: boolean; message: string }>(`/admin/cookies/${accountId}`),

  ban: (accountId: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/cookies/${accountId}/ban`),

  unban: (accountId: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/cookies/${accountId}/unban`),

  test: (data: { id: string }) =>
    client.post<{ success: boolean; message?: string }>('/admin/cookies/test', data),

  options: () =>
    client.get<{ items: CookieOption[] }>('/admin/cookies/options'),

  status: () =>
    client.get<CookieStatusSummary>('/admin/cookies/status'),

  replace: (data: { dbcl2: string; bid?: string }) =>
    client.post<{ success: boolean; account_id: string }>('/admin/cookies/replace', data),
}
