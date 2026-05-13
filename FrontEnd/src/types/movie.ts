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
  is_published?: boolean
}

export interface Person {
  id: number
  name: string
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
