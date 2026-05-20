import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { PermissionCode } from '@/utils/permission'

export function setupGuards(router: Router): void {
  router.beforeEach(async (to, _from, next) => {
    const authStore = useAuthStore()

    if (to.meta.requiresAuth) {
      if (!authStore.token) {
        next({ name: 'Login', query: { redirect: to.fullPath } })
        return
      }

      if (!authStore.user) {
        try {
          await authStore.fetchUser()
        } catch {
          next({ name: 'Login', query: { redirect: to.fullPath } })
          return
        }
      }

      // 特殊处理：直接访问/admin根路径时，自动跳转到第一个有权限的管理页面
      if (to.path === '/admin' && authStore.isAdmin) {
        const pages = [
          { path: '/admin', permission: 'system:monitor' },
          { path: '/admin/movies', permission: 'movie:read' },
          { path: '/admin/reviews', permission: 'comment:read' },
          { path: '/admin/crawler', permission: 'crawler:task:write' },
          { path: '/admin/douban-ids', permission: 'crawler:task:read' },
          { path: '/admin/users', permission: 'user:manage' },
          { path: '/admin/infra', permission: 'system:monitor' },
        ] as const

        for (const page of pages) {
          if (authStore.checkPermission(page.permission)) {
            if (page.path === '/admin') {
              // 如果匹配到仪表盘，直接放行，避免重定向循环
              next()
            } else {
              next({ path: page.path })
            }
            return
          }
        }
      }

      if (to.meta.permission) {
        const requiredPermission = to.meta.permission as PermissionCode
        if (!authStore.checkPermission(requiredPermission)) {
          next({ name: 'Forbidden' })
          return
        }
      }
    }

    next()
  })
}
