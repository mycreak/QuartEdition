import client from '@/api/client'
import type { SystemStatus, QueueStatus } from '@/types/status'

export const adminStatusApi = {
  get: () => client.get<SystemStatus>('/admin/status'),
}

export const adminQueueApi = {
  get: (details?: boolean) =>
    client.get<QueueStatus>('/admin/tasks/queue', { params: details ? { details: '1' } : {} }),
  fetchDetails: () =>
    client.get<QueueStatus>('/admin/tasks/queue', { params: { details: '1' } }),
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
