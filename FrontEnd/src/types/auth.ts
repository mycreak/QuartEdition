export interface User {
  id: number
  uuid?: number
  username: string
  display_name: string
  role: 'admin' | 'user'
  permissions: string[]
  is_active?: boolean
  avatar_url?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  password: string
  display_name?: string
}

export interface LoginResponse {
  token: string
  user: {
    uuid: number
    username: string
    display_name: string
  }
}
