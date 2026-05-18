export interface SystemStatus {
  puller_state?: string
  puller_fetched?: number
  puller_empty_polls?: number
  queue_size?: number
  queue_maxsize?: number
  queue_saturation?: number
  worker_alive?: number
  worker_busy?: number
  worker_idle?: number
  worker_cooldown?: number
  worker_cooldown_info?: Array<{ worker_id: number; cooldown_remaining: number }>
  worker_dead?: number
  worker_stuck?: number
  cpu_percent?: number
  memory_percent?: number
  db_mysql: boolean
  db_redis: boolean
  db_mongodb?: boolean
  cookie_saved_at?: string | null
  cookie_has_dbcl2?: boolean
  cookie_valid?: boolean
  proxy?: {
    alive: number
    suspicious: number
    banned: number
    total: number
  }
}

export interface TaskSummary {
  type: string
  task_id: number
  admin_id: number
  type_num?: number
  interval_id?: string
  douban_id?: string
  cookie_id?: string
  proxy_key?: string
  review_id?: string
  movie_id?: number
  label: string
}

export interface InFlightTask extends TaskSummary {
  worker_id: number
  busy_seconds: number
  stage?: string
}

export interface QueueStatus {
  redis_size: number
  queue_size: number
  worker_busy: number
  worker_idle: number
  worker_cooldown: number
  redis_tasks?: TaskSummary[]
  queue_tasks?: TaskSummary[]
  in_flight?: InFlightTask[]
}
