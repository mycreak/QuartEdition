export function formatRating(value: number | string | undefined | null): string {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (num == null || isNaN(num)) {
    return '暂无评分'
  }
  return num.toFixed(1)
}

export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) {
    return ''
  }
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) {
    return dateStr
  }
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function formatDateTime(dateStr: string | undefined | null): string {
  if (!dateStr) {
    return ''
  }
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) {
    return dateStr
  }
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d} ${h}:${min}`
}

export function formatCount(value: number | undefined | null): string {
  if (value == null || isNaN(value)) {
    return '0'
  }
  if (value >= 10000) {
    return (value / 10000).toFixed(1) + '万'
  }
  return String(value)
}

const CREW_ROLE_MAP: Record<string, string> = {
  writer: '编剧',
  producer: '制片人',
  art_director: '美术指导',
  music: '音乐',
  other: '其他',
  director: '导演',
  actor: '演员',
}

export function formatCrewRole(role: string): string {
  return CREW_ROLE_MAP[role] || role
}

/**
 * 清理URL中的多余字符（反引号、空格等）
 */
export function cleanUrl(url: string | null | undefined): string {
  if (!url) return ''
  // 去掉前后的空格和反引号
  return url.replace(/^[\s`]+|[\s`]+$/g, '')
}
