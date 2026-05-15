const PERMISSION_CODES = [
  'user:manage',
  'crawler:task:read',
  'crawler:task:write',
  'crawler:failure:manage',
  'movie:manage',
  'movie:read',
  'comment:read',
  'comment:manage',
  'system:monitor',
  'infra:proxy:read',
  'infra:proxy:manage',
  'infra:cookie:read',
  'infra:cookie:manage',
  'infra:sensitive:read',
] as const

export type PermissionCode = (typeof PERMISSION_CODES)[number]

const PERMISSION_DESCRIPTIONS: Record<PermissionCode, string> = {
  'user:manage': '用户管理 — 创建用户、分配角色权限',
  'crawler:task:read': '任务查看 — 查看任务进度、任务历史',
  'crawler:task:write': '任务提交 — 提交爬虫抓取任务',
  'crawler:failure:manage': '失败管理 — 认领、解决、重试失败任务',
  'movie:manage': '电影管理 — 上架/下架电影',
  'movie:read': '电影查看 — 浏览电影数据',
  'comment:read': '评论查看 — 浏览评论和短评',
  'comment:manage': '评论管理 — 审核上架/下架评论',
  'system:monitor': '系统监控 — 查看实时状态、队列、日志、限流事件',
  'infra:proxy:read': '代理查看 — 查看代理池列表、状态',
  'infra:proxy:manage': '代理管理 — 添加、删除、验证代理',
  'infra:cookie:read': 'Cookie查看 — 查看Cookie账号列表、状态',
  'infra:cookie:manage': 'Cookie管理 — 添加、删除、验证Cookie账号',
  'infra:sensitive:read': '敏感信息查看 — 查看代理密码、完整Cookie值等敏感信息',
}

export function hasPermission(
  userPermissions: string[] | undefined | null,
  required: PermissionCode | PermissionCode[]
): boolean {
  if (!userPermissions || userPermissions.length === 0) {
    return false
  }
  const requiredList = Array.isArray(required) ? required : [required]
  return requiredList.every((code) =>
    userPermissions.includes(code) ||
    (code.startsWith('infra:') && userPermissions.includes('system:monitor'))
  )
}

export function getPermissionShortName(code: string): string {
  const desc = PERMISSION_DESCRIPTIONS[code as PermissionCode]
  if (!desc) return code
  const dashIndex = desc.indexOf(' — ')
  return dashIndex === -1 ? desc : desc.slice(0, dashIndex)
}

export { PERMISSION_CODES, PERMISSION_DESCRIPTIONS }
