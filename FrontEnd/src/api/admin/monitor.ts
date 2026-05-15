import client from '@/api/client'
import type { SystemStatus, QueueStatus } from '@/types/status'

export const adminStatusApi = {
  get: () => client.get<SystemStatus>('/admin/status'),
}

export const adminQueueApi = {
  get: (params?: { details?: boolean; admin_id?: number }) =>
    client.get<QueueStatus>('/admin/tasks/queue', { params: params || {} }),
  fetchDetails: (adminId?: number) =>
    client.get<QueueStatus>('/admin/tasks/queue', { params: { details: '1', ...(adminId ? { admin_id: adminId } : {}) } }),
}

export interface LogEntry {
  timestamp: string
  level: string
  logger: string
  category: string
  message: string
  module: string
  line: number
}

export interface LogsResponse {
  items: LogEntry[]
  total: number
  page: number
  page_size: number
  latest_timestamp: string
}

export const adminLogsApi = {
  list: (params: { level?: string; category?: string; since?: string; limit?: number; offset?: number }) =>
    client.get<LogsResponse>('/admin/logs', { params }),
}

export interface RateLimitEvent {
  endpoint: string
  identifier: string
  count: number
  max_requests: number
  window_seconds: number
  timestamp: string
}

export interface RateLimitResponse {
  endpoints: Record<string, { total: number; window_seconds: number; max_requests: number }>
  events: RateLimitEvent[]
  total_events: number
}

export const adminRateLimitApi = {
  list: (params: { minutes?: number; endpoint?: string }) =>
    client.get<RateLimitResponse>('/admin/rate-limit-events', { params }),
}

export const adminDebugApi = {
  pushEvent: (data: { event_type: 'task_failure' | 'worker_crash' }) =>
    client.post<{ success: boolean; event_type: string; message: string }>('/admin/debug/ws-event', data),
}
