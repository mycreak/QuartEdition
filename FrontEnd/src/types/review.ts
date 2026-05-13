export interface Review {
  id: number
  movie_id: number
  title: string
  content: string
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
}
