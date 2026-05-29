export interface Movie {
  id: number
  douban_id: string
  title: string
  release_year?: number
  poster_url?: string
  rating?: {
    average: number
    count: number
  }
  genres: string[]
  regions?: string[] | Region[]
  ai_summary?: string
  ai_tags?: string[]
  is_published?: boolean
}

export interface Person {
  id: number
  name: string
  douban_id?: string
}

export interface Genre {
  id: number
  name: string
  is_published?: number
}

export interface Region {
  id: number
  name: string
}

export interface RatingDistribution {
  average: number
  count: number
  distribution?: Record<string, number>
}

export interface MovieDetail {
  movie: Movie
  rating?: RatingDistribution
  directors: Person[]
  actors: Person[]
  crew: Record<string, Person[]>
  genres: Genre[]
  regions: Region[]
  ai_summary?: string
  ai_tags?: string[]
}

export interface WordCloudItem {
  text: string
  weight: number
}

/** 用户对单部电影的标记状态 */
export interface MovieStatus {
  movie_id: number
  want_watch: boolean
  watching: boolean
  watched: boolean
  favorite: boolean
  reviewed: boolean
}

/** 片单 — 轮播列表项 */
export interface PlaylistBrief {
  id: number
  title: string
  description: string
  cover_url: string
  sort_order: number
}

/** 片单详情 — 含电影摘要 */
export interface PlaylistDetail {
  id: number
  title: string
  description: string
  cover_url: string
  sort_order: number
  movies: PlaylistMovie[]
}

export interface PlaylistMovie {
  id: number
  title: string
  poster_url?: string
  release_year?: number
  rating?: number
  ai_summary?: string
}
