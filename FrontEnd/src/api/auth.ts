import client from './client'
import type { LoginRequest, LoginResponse, RegisterRequest, User } from '@/types/auth'

export const authApi = {
  login: (data: LoginRequest) =>
    client.post<LoginResponse>('/auth/login', data),

  register: (data: RegisterRequest) =>
    client.post<{ id: number; username: string; message: string }>(
      '/auth/register',
      data
    ),

  me: () => client.get<User>('/auth/me'),
}
