import client from '@/api/client'

export interface ProxyItem {
  host: string
  port: number
  region: string
  source: string
  is_alive: boolean
  success_rate: number
  avg_latency_ms: number
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
  allowed_regions: string[]
  dbcl2_preview: string
  saved_at: string
  state: 'active' | 'suspicious' | 'banned'
  last_used_at: number
  fail_count: number
  success_count: number
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

export const adminProxyApi = {
  list: () =>
    client.get<{ proxies: ProxyItem[]; stats: ProxyStats }>('/admin/proxies'),

  add: (data: { host: string; port: number; region?: string }) =>
    client.post<{ success: boolean; key: string }>('/admin/proxies', data),

  remove: (host: string, port: number) =>
    client.delete<{ success: boolean; key: string }>(`/admin/proxies/${host}/${port}`),

  healthCheck: () =>
    client.post<Record<string, unknown>>('/admin/proxies/health-check'),
}

export const adminCookieApi = {
  list: () =>
    client.get<{ items: CookieAccount[]; stats: CookieStats }>('/admin/cookies'),

  add: (data: {
    dbcl2: string
    allowed_regions: string[]
    bid?: string
    label?: string
  }) =>
    client.post<{ success: boolean; account_id: string }>('/admin/cookies', data),

  remove: (accountId: string) =>
    client.delete<{ success: boolean; message: string }>(`/admin/cookies/${accountId}`),

  ban: (accountId: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/cookies/${accountId}/ban`),

  unban: (accountId: string) =>
    client.post<{ success: boolean; message: string }>(`/admin/cookies/${accountId}/unban`),

  status: () =>
    client.get<CookieStatusSummary>('/admin/cookies/status'),

  replace: (data: { dbcl2: string; bid?: string }) =>
    client.post<{ success: boolean; account_id: string }>('/admin/cookies/replace', data),
}
