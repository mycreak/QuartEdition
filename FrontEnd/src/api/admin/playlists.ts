import client from '../client'
import type { PlaylistBrief, PlaylistDetail } from '@/types/movie'

export interface PlaylistFull {
  id: number
  title: string
  description: string
  cover_url: string
  movie_ids: number[]
  sort_order: number
  is_published: number
  publish_at: string | null
  unpublish_at: string | null
  created_by: number
  created_at: string
  updated_at: string
}

export const adminPlaylistApi = {
  list: (params?: {
    keyword?: string
    created_by?: number
    created_after?: string
    created_before?: string
    publish_after?: string
    publish_before?: string
    is_published?: number
  }) =>
    client.get<{ items: PlaylistFull[]; total: number }>('/admin/playlists', { params }),

  create: (data: {
    title: string
    movie_ids: number[]
    description?: string
    cover_url?: string
    sort_order?: number
    publish_at?: string | null
    unpublish_at?: string | null
  }) =>
    client.post<{ success: boolean; data: PlaylistFull }>('/admin/playlists', data),

  update: (id: number, data: Partial<{
    title: string
    movie_ids: number[]
    description: string
    cover_url: string
    sort_order: number
    publish_at: string | null
    unpublish_at: string | null
  }>) =>
    client.put<{ success: boolean; data: PlaylistFull }>(`/admin/playlists/${id}`, data),

  delete: (id: number) =>
    client.delete<{ success: boolean; message: string }>(`/admin/playlists/${id}`),

  publish: (id: number) =>
    client.post<{ success: boolean; data: PlaylistFull }>(`/admin/playlists/${id}/publish`),

  unpublish: (id: number) =>
    client.post<{ success: boolean; data: PlaylistFull }>(`/admin/playlists/${id}/unpublish`),
}
