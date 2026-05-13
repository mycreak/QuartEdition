import client from '@/api/client'
import type { User } from '@/types/auth'

/**
 * 更新当前用户个人信息
 * @param params - 要更新的字段，仅支持display_name和avatar_url
 */
export const updateProfile = (params: {
  display_name?: string
  avatar_url?: string
}) => {
  return client.patch<{
    success: boolean
    message: string
    data: User
  }>('/auth/me', params)
}

/**
 * 上传用户头像
 * @param file - 头像文件对象
 */
export const uploadAvatar = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return client.post<{
    success: boolean
    message: string
    data: {
      avatar_url: string
    }
  }>('/user/upload/avatar', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export default {
  updateProfile,
  uploadAvatar
}
