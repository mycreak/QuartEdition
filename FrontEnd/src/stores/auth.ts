import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, LoginRequest, RegisterRequest } from '@/types/auth'
import { authApi } from '@/api/auth'
import { hasPermission, type PermissionCode } from '@/utils/permission'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))

  const isAdmin = computed(() => user.value?.role === 'admin')

  const isLoggedIn = computed(() => !!token.value)

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  async function login(credentials: LoginRequest): Promise<void> {
    const res = await authApi.login(credentials)
    token.value = res.data.token
    localStorage.setItem('token', res.data.token)
    await fetchUser()
  }

  async function register(data: RegisterRequest): Promise<void> {
    await authApi.register(data)
  }

  async function fetchUser(): Promise<void> {
  if (!token.value) {
    return
  }
  try {
    const res = await authApi.me()
    user.value = res.data
  } catch (_err) {
    user.value = null
  }
}

/** 更新个人信息 */
async function updateProfile(newUser: User) {
  if (user.value) {
    user.value = { ...user.value, ...newUser }
  }
  return Promise.resolve()
}

function checkPermission(code: PermissionCode | PermissionCode[]): boolean {
  return hasPermission(user.value?.permissions, code)
}

  return {
    user,
    token,
    isAdmin,
    isLoggedIn,
    login,
    register,
    fetchUser,
    logout,
    checkPermission,
    updateProfile,
  }
})
