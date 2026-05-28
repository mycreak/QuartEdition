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

/**
 * 上传片单封面
 * @param file - 封面文件对象
 */
export const uploadListCover = (file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  return client.post<{
    success: boolean
    message: string
    data: {
      cover_url: string
    }
  }>("/admin/upload/list-cover", formData, {
    headers: {
      "Content-Type": "multipart/form-data"
    }
  })
}

/**
 * 修改当前用户密码
 * @param oldPassword - 原密码
 * @param newPassword - 新密码（≥6位+大小写字母+数字）
 */
export const changePassword = (oldPassword: string, newPassword: string) => {
  return client.patch<{
    success: boolean
    message: string
  }>('/auth/me/password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}

export default {
  updateProfile,
  uploadAvatar,
  uploadListCover,
  changePassword
}
