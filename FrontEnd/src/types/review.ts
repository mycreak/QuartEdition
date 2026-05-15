export interface Review {
  id: number | string
  _id?: string
  movie_id: number
  title: string
  content: string
  text?: string
  author: string
  rating?: number
  is_published?: boolean
  created_at: string
}

export interface Comment {
  id: number
  movie_id: number
  content: string
  author: string
  rating?: number
  is_published?: boolean
  created_at: string
  // 兼容历史字段名
  text?: string
}
