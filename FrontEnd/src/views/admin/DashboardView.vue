<template>
  <div class="dashboard-page">
    <h2 class="page-title">系统仪表盘</h2>

    <div class="status-grid">
      <el-card v-if="authStore.checkPermission('system:monitor')" class="status-card">
        <div class="card-header">
          <span class="card-icon">🔄</span>
          <span class="card-label">Puller 状态</span>
        </div>
        <el-tag :type="sys.puller_state === 'running' ? 'success' : 'danger'" size="large">
          {{ sys.puller_state === 'running' ? '运行中' : sys.puller_state || '未知' }}
        </el-tag>
        <div class="card-detail" v-if="sys.puller_fetched != null">已拉取: {{ sys.puller_fetched }} 条 | 空轮询: {{ sys.puller_empty_polls }} 次</div>
      </el-card>

      <el-card v-if="authStore.checkPermission('system:monitor')" class="status-card">
        <div class="card-header"><span class="card-icon">⚙️</span><span class="card-label">Worker 状态</span></div>
        <div class="worker-stats">
          <span class="worker-num alive">{{ sys.worker_alive }} 存活</span>
          <span class="worker-num busy">{{ sys.worker_busy }} 忙碌</span>
          <span class="worker-num idle">{{ sys.worker_idle }} 空闲</span>
        </div>
      </el-card>

      <el-card v-if="authStore.checkPermission('system:monitor')" class="status-card">
        <div class="card-header"><span class="card-icon">📦</span><span class="card-label">任务队列</span></div>
        <el-progress :percentage="Math.round((sys.queue_size || 0) / (sys.queue_maxsize || 1) * 100)" :stroke-width="18">
          <span>{{ sys.queue_size }} / {{ sys.queue_maxsize }}</span>
        </el-progress>
      </el-card>

      <el-card class="status-card" :class="{ 'card-warn': cpuAlert }">
        <div class="card-header"><span class="card-icon">💻</span><span class="card-label">系统资源</span></div>
        <div class="resource-row"><span>CPU</span><el-progress :percentage="sys.cpu_percent || 0" :color="cpuColor" :stroke-width="12" /></div>
        <div class="resource-row"><span>内存</span><el-progress :percentage="sys.memory_percent || 0" :color="memColor" :stroke-width="12" /></div>
      </el-card>

      <el-card class="status-card">
        <div class="card-header"><span class="card-icon">🗄️</span><span class="card-label">数据库</span></div>
        <div class="db-row"><span :class="sys.db_mysql ? 'db-up' : 'db-down'">MySQL {{ sys.db_mysql ? '🟢' : '🔴' }}</span></div>
        <div class="db-row"><span :class="sys.db_redis ? 'db-up' : 'db-down'">Redis {{ sys.db_redis ? '🟢' : '🔴' }}</span></div>
        <div class="db-row"><span :class="sys.db_mongodb ? 'db-up' : 'db-down'">MongoDB {{ sys.db_mongodb ? '🟢' : '🔴' }}</span></div>
      </el-card>

      <el-card v-if="authStore.checkPermission('system:monitor')" class="status-card" :class="{ 'card-warn': !sys.cookie_valid }">
        <div class="card-header"><span class="card-icon">🍪</span><span class="card-label">豆瓣 Cookie</span></div>
        <el-tag :type="sys.cookie_valid ? 'success' : 'danger'" size="large">{{ sys.cookie_valid ? '有效' : sys.cookie_has_dbcl2 ? '待验证' : '缺失' }}</el-tag>
        <div class="card-detail" v-if="sys.cookie_saved_at">上次保存: {{ sys.cookie_saved_at }}</div>
      </el-card>

      <el-card v-if="authStore.checkPermission('system:monitor')" class="status-card">
        <div class="card-header"><span class="card-icon">🌐</span><span class="card-label">代理池</span></div>
        <div class="proxy-stats" v-if="sys.proxy">
          <span class="proxy-num alive">{{ sys.proxy.alive }}</span><span class="proxy-label">存活</span>
          <span class="proxy-num suspicious">{{ sys.proxy.suspicious }}</span><span class="proxy-label">可疑</span>
          <span class="proxy-num banned">{{ sys.proxy.banned }}</span><span class="proxy-label">封禁</span>
        </div>
        <div class="card-detail" v-if="sys.proxy">共 {{ sys.proxy.total }} 个代理</div>
      </el-card>
    </div>

    <div class="grid-2col">
      <el-card v-if="authStore.checkPermission('system:monitor')" class="section-card">
        <template #header><div class="section-title">⏱️ 队列状态 <el-tag size="small" class="refresh-tag" @click="fetchQueue">刷新</el-tag> <el-switch v-model="showDetails" size="small" style="margin-left:8px" active-text="详情" @change="onDetailsToggle" /></div></template>
        <div class="queue-panel" v-loading="queueLoading">
          <div class="queue-item" v-if="queue.redis_size > 0">
            <el-tag type="info" size="large">🔵 等待调度 ({{ queue.redis_size }} 个任务)</el-tag>
            <span class="queue-sub">Redis ZSET 中待 Puller 拉取</span>
          </div>
          <div class="queue-item" v-if="queue.queue_size > 0">
            <el-tag type="warning" size="large">🟡 队列待消费 ({{ queue.queue_size }} 个任务)</el-tag>
          </div>
          <div class="queue-item" v-if="queue.worker_busy > 0">
            <el-tag type="success" size="large">🟢 Worker 工作中 ({{ queue.worker_busy }} 忙碌 / {{ queue.worker_idle }} 空闲)</el-tag>
          </div>
          <div class="queue-item" v-if="queue.redis_size === 0 && queue.queue_size === 0 && queue.worker_busy === 0 && !queueLoading">
            <el-tag type="success" size="large">✅ 空闲 — 无待处理任务</el-tag>
          </div>

          <template v-if="showDetails && detailLoading">
            <div class="queue-sub" style="margin-top:8px">🔄 加载详情...</div>
          </template>
          <template v-else-if="showDetails">
            <div v-if="queue.in_flight?.length" class="detail-section">
              <div class="detail-section-title">🔵 执行中 ({{ queue.in_flight.length }})</div>
              <div v-for="t in queue.in_flight" :key="t.task_id" class="task-detail-row">
                <el-tag size="small" :type="t.type === 'movie_scrape_task' ? 'warning' : 'info'">{{ typeLabel(t.type) }}</el-tag>
                <span class="task-detail-label">{{ t.label }}</span>
                <span class="task-detail-stage" v-if="t.stage">{{ t.stage }}</span>
                <span class="task-detail-seconds">{{ t.busy_seconds?.toFixed(0) }}s</span>
              </div>
            </div>
            <div v-if="queue.queue_tasks?.length" class="detail-section">
              <div class="detail-section-title">🟡 队列中 ({{ queue.queue_tasks.length }})</div>
              <div v-for="t in queue.queue_tasks" :key="t.task_id" class="task-detail-row">
                <el-tag size="small" type="warning">{{ t.type }}</el-tag>
                <span class="task-detail-label">{{ t.label }}</span>
              </div>
            </div>
            <div v-if="queue.redis_tasks?.length" class="detail-section">
              <div class="detail-section-title">⚪ Redis 待拉取 ({{ queue.redis_tasks.length }}，仅前 20)</div>
              <div v-for="t in queue.redis_tasks" :key="t.task_id" class="task-detail-row">
                <el-tag size="small" type="info">{{ t.type }}</el-tag>
                <span class="task-detail-label">{{ t.label }}</span>
              </div>
            </div>
          </template>
        </div>
      </el-card>

      <el-card v-if="authStore.checkPermission('system:monitor')" class="section-card">
        <template #header><div class="section-title">🛡️ 安全 <el-tag size="small" class="refresh-tag" @click="fetchRateLimit">刷新</el-tag></div></template>
        <div v-if="rateLimit.total_events === 0 && !limitLoading" class="safe-ok">🟢 无异常 IP 限流事件</div>
        <div v-else v-loading="limitLoading">
          <div class="limit-summary">最近 60 分钟: <el-tag type="danger">{{ rateLimit.total_events }} 次限流</el-tag></div>
          <div class="limit-list">
            <div v-for="(evt, i) in rateLimit.events" :key="i" class="limit-item">
              <span class="limit-ip">{{ evt.identifier }}</span>
              <span class="limit-info">{{ evt.count }} 次 / {{ evt.window_seconds }}s (上限 {{ evt.max_requests }})</span>
              <span class="limit-time">{{ evt.timestamp }}</span>
            </div>
          </div>
          <div class="limit-rules">
            <el-tag v-for="(cfg, key) in rateLimit.endpoints" :key="key" size="small" type="info">{{ key }}: {{ cfg.max_requests }}次/{{ cfg.window_seconds }}秒</el-tag>
          </div>
        </div>
      </el-card>
    </div>

    <el-card v-if="authStore.checkPermission('system:monitor')" class="section-card">
      <template #header><div class="section-title">📋 最近日志 (ERROR)</div></template>
      <div class="log-list" v-loading="logLoading">
        <div v-for="(log, i) in logs" :key="i" class="log-item">
          <span class="log-time">{{ log.timestamp }}</span>
          <el-tag :type="log.level === 'ERROR' ? 'danger' : 'warning'" size="small">{{ log.level }}</el-tag>
          <span class="log-category">{{ log.category }}</span>
          <span class="log-msg">{{ log.message }}</span>
        </div>
        <div v-if="!logLoading && logs.length === 0" class="safe-ok">暂无日志</div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { adminStatusApi } from '@/api/admin/monitor'
import { adminQueueApi } from '@/api/admin/monitor'
import { adminLogsApi, type LogEntry } from '@/api/admin/monitor'
import { adminRateLimitApi, type RateLimitEvent, type RateLimitResponse } from '@/api/admin/monitor'
import { wsManager } from '@/api/ws'

function typeLabel(t: string): string {
  const m: Record<string, string> = { movie_crawl: '电影抓取', movie_scrape_task: '详情爬取', review_crawl: '长评列表', review_body_crawl: '长评正文', comment_crawl: '短评抓取' }
  return m[t] || t
}

const authStore = useAuthStore()
const sys = reactive({
  puller_state: '' as string, puller_fetched: null as number | null, puller_empty_polls: null as number | null,
  queue_size: 0, queue_maxsize: 1000,
  worker_alive: 0, worker_busy: 0, worker_idle: 0,
  cpu_percent: null as number | null, memory_percent: null as number | null,
  db_mysql: false, db_redis: false, db_mongodb: false,
  cookie_saved_at: null as string | null, cookie_has_dbcl2: false, cookie_valid: false,
  proxy: undefined as { alive: number; suspicious: number; banned: number; total: number } | undefined,
})

const queue = reactive({ redis_size: 0, queue_size: 0, worker_busy: 0, worker_idle: 0 })
const queueLoading = ref(false)
const showDetails = ref(false)
const detailLoading = ref(false)

const rateLimit = reactive<RateLimitResponse & { events: RateLimitEvent[] }>({
  endpoints: {}, events: [], total_events: 0,
})
const limitLoading = ref(false)

const logs = reactive<LogEntry[]>([])
const logLoading = ref(false)

const cpuAlert = computed(() => (sys.cpu_percent || 0) > 80)
const cpuColor = computed(() => { const v = sys.cpu_percent || 0; if (v > 80) return '#f56c6c'; if (v > 60) return '#e6a23c'; return '#67c23a' })
const memColor = computed(() => { const v = sys.memory_percent || 0; if (v > 85) return '#f56c6c'; if (v > 70) return '#e6a23c'; return '#67c23a' })

let unsubStatus: (() => void) | null = null
let unsubProgress: (() => void) | null = null
let _lastWsUpdate = 0

async function fetchStatus() {
  try {
    const res = await adminStatusApi.get()
    Object.assign(sys, res.data)
  } catch { /* ignore */ }
}

async function fetchQueue(details = false) {
  queueLoading.value = true
  try {
    const res = await adminQueueApi.get(details)
    Object.assign(queue, res.data)
  } catch { /* ignore */ } finally { queueLoading.value = false }
}

async function onDetailsToggle(on: boolean) {
  if (!on) return
  detailLoading.value = true
  try {
    const res = await adminQueueApi.fetchDetails()
    Object.assign(queue, res.data)
  } catch { /* ignore */ } finally { detailLoading.value = false }
}

async function fetchLogs() {
  logLoading.value = true
  try {
    const res = await adminLogsApi.list({ level: 'ERROR', limit: 20 })
    logs.splice(0, logs.length, ...res.data.items)
  } catch { /* ignore */ } finally { logLoading.value = false }
}

async function fetchRateLimit() {
  limitLoading.value = true
  try {
    const res = await adminRateLimitApi.list({ minutes: 60 })
    Object.assign(rateLimit, res.data)
  } catch { /* ignore */ } finally { limitLoading.value = false }
}

onMounted(() => {
  fetchStatus()
  if (authStore.checkPermission('system:monitor')) {
    fetchQueue()
    fetchLogs()
    fetchRateLimit()
  }

  unsubStatus = wsManager.on('system_status', (msg) => {
    const now = Date.now()
    if (now - _lastWsUpdate < 1000) return
    _lastWsUpdate = now

    Object.assign(sys, {
      puller_state: msg.puller_state,
      puller_fetched: msg.puller_fetched,
      puller_empty_polls: msg.puller_empty_polls,
      queue_size: msg.queue_size,
      queue_maxsize: msg.queue_maxsize,
      worker_alive: msg.worker_alive,
      worker_busy: msg.worker_busy,
      worker_idle: msg.worker_idle,
      cpu_percent: msg.cpu_percent,
      memory_percent: msg.memory_percent,
      db_mysql: msg.db_mysql,
      db_redis: msg.db_redis,
      db_mongodb: msg.db_mongodb,
      cookie_saved_at: msg.cookie_saved_at,
      cookie_has_dbcl2: msg.cookie_has_dbcl2,
      cookie_valid: msg.cookie_valid,
      proxy: msg.proxy ?? sys.proxy,
    })

    Object.assign(queue, {
      redis_size: msg.redis_size ?? queue.redis_size,
      queue_size: msg.queue_size ?? queue.queue_size,
      worker_busy: msg.worker_busy ?? queue.worker_busy,
      worker_idle: msg.worker_idle ?? queue.worker_idle,
    })
  })

  unsubProgress = wsManager.on('task_progress', (msg) => {
    if (!queue.in_flight) return
    const task = queue.in_flight.find(t => t.task_id === msg.task_id)
    if (task) {
      task.stage = msg.stage
    }
  })
})

onUnmounted(() => {
  unsubStatus?.()
  unsubStatus = null
  unsubProgress?.()
  unsubProgress = null
})
</script>

<style scoped>
.dashboard-page { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 24px; }
.status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }
.status-card { border-radius: 8px; }
.status-card .card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.status-card .card-icon { font-size: 20px; }
.status-card .card-label { font-weight: 600; font-size: 15px; color: #333; }
.status-card .card-detail { margin-top: 8px; font-size: 12px; color: #999; }
.status-card.card-warn { border: 1px solid #f56c6c; }
.worker-stats { display: flex; gap: 12px; }
.worker-num { font-size: 20px; font-weight: 700; }
.worker-num.alive { color: #67c23a; }
.worker-num.busy { color: #e6a23c; }
.worker-num.idle { color: #909399; }
.proxy-stats { display: flex; gap: 4px; align-items: baseline; }
.proxy-num { font-size: 22px; font-weight: 700; margin-right: 2px; }
.proxy-num.alive { color: #67c23a; }
.proxy-num.suspicious { color: #e6a23c; }
.proxy-num.banned { color: #f56c6c; }
.proxy-label { font-size: 12px; color: #909399; margin-right: 10px; }
.detail-section { margin-top: 10px; }
.detail-section-title { font-size: 12px; color: #606266; font-weight: 600; margin: 8px 0 4px; }
.task-detail-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.task-detail-label { color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-detail-stage { color: #909399; font-size: 12px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-detail-seconds { color: #e6a23c; font-size: 12px; font-weight: 600; white-space: nowrap; }
.resource-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.resource-row span { width: 32px; color: #666; }
.resource-row .el-progress { flex: 1; }
.db-row { font-size: 14px; margin-bottom: 4px; }
.db-up { color: #67c23a; }
.db-down { color: #f56c6c; }
.grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
@media (max-width: 768px) { .grid-2col { grid-template-columns: 1fr; } }
.section-card { border-radius: 8px; }
.section-title { font-size: 15px; font-weight: 600; color: #1a1a2e; display: flex; align-items: center; justify-content: space-between; }
.refresh-tag { cursor: pointer; }
.queue-panel { display: flex; flex-direction: column; gap: 10px; min-height: 60px; }
.queue-item { display: flex; flex-direction: column; gap: 4px; }
.queue-sub { font-size: 12px; color: #999; }
.safe-ok { color: #67c23a; font-size: 15px; font-weight: 500; }
.limit-summary { margin-bottom: 10px; }
.limit-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.limit-item { display: flex; align-items: center; gap: 8px; font-size: 13px; background: #fff2f0; padding: 6px 10px; border-radius: 4px; }
.limit-ip { font-weight: 600; color: #a8071a; font-family: monospace; }
.limit-info { color: #555; }
.limit-time { color: #999; font-size: 12px; margin-left: auto; }
.limit-rules { display: flex; gap: 8px; flex-wrap: wrap; }
.log-list { display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; min-height: 40px; }
.log-item { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
.log-time { color: #999; font-size: 12px; white-space: nowrap; }
.log-category { color: #666; font-size: 12px; background: #f0f0f0; padding: 1px 6px; border-radius: 3px; }
.log-msg { flex: 1; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
