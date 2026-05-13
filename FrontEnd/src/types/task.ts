export interface TaskSubmit {
  type: 'movie_crawl' | 'review_crawl' | 'comment_crawl' | 'review_body_crawl' | 'movie_scrape_task'
  type_num?: number
  interval_id?: string
  douban_id?: string
  comment_pages?: number
  cookie_id?: string
  proxy_key?: string
  review_id?: string
  title?: string
  author?: string
}

export interface TaskSubmitResponse {
  task_id: number
  type: string
  execute_at: number
  url: string
  skipped?: boolean
  reason?: string
  message?: string
}

export interface MovieWithPendingReviews {
  movie_id: number
  title: string
  pending_count: number
  douban_id?: string
}

export interface PendingReview {
  review_id: string
  title: string
  author: string
  useful_count: number
  date: string
}

export interface TaskProgress {
  id: number
  type: string
  interval_id?: string
  crawled: number
  total: number
  done: boolean
  created_at: string
}
