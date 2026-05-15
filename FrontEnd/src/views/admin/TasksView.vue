<template>
  <div class="crawler-page">
    <h2 class="page-title">爬虫面板</h2>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="任务提交" name="submit">
        <el-card class="task-card">
          <el-form :model="taskForm" label-position="top" style="max-width: 550px">
            <el-form-item label="任务类型">
              <el-select v-model="taskForm.type" placeholder="选择任务类型" style="width: 100%" @change="onTypeChange">
                <el-option label="类型1: 电影抓取 (榜单)" value="movie_crawl" />
                <el-option label="类型2: 长评列表抓取" value="review_crawl" />
                <el-option label="类型3: 短评抓取" value="comment_crawl" />
                <el-option label="类型4: 长评正文抓取" value="review_body_crawl" />
                <el-option label="类型5: 单部电影详情爬取" value="movie_scrape_task" />
              </el-select>
            </el-form-item>

            <template v-if="taskForm.type === 'movie_crawl'">
              <el-form-item label="豆瓣类型">
                <el-select v-model="taskForm.type_num" placeholder="选择类型" style="width: 100%">
                  <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
                </el-select>
              </el-form-item>
              <el-form-item label="评分区间">
                <el-select v-model="taskForm.interval_id" placeholder="选择评分区间" style="width: 100%">
                  <el-option v-for="iv in intervalOptions" :key="iv.interval_id" :label="iv.label" :value="iv.interval_id" />
                </el-select>
              </el-form-item>
            </template>

            <template v-if="taskForm.type === 'review_crawl'">
      <el-form-item label="豆瓣电影 ID (douban_id)">
        <el-input v-model="taskForm.douban_id" placeholder="如 1292052" />
      </el-form-item>
      <el-form-item label="列表翻页数">
        <el-input-number v-model="taskForm.pages" :min="1" :max="10" style="width: 100%" />
      </el-form-item>
      <el-form-item label="Cookie 身份">
        <CookieSelector v-model="taskForm.review_cookie_id" />
        <div class="form-hint">选填，不选则使用游客模式</div>
      </el-form-item>
      <el-form-item label="代理">
        <ProxySelector v-model="taskForm.review_proxy_key" />
        <div class="form-hint">选填，不选则使用直连</div>
      </el-form-item>
    </template>

            <template v-if="taskForm.type === 'review_body_crawl'">
              <el-form-item label="选择电影">
                <el-select
                  v-model="taskForm.selected_movie_id"
                  placeholder="选择有未爬长评的电影"
                  clearable
                  filterable
                  style="width: 100%"
                  :loading="moviesLoading"
                  @change="onMovieSelect"
                >
                  <el-option
                    v-for="movie in moviesWithPendingReviews"
                    :key="movie.movie_id"
                    :label="`${movie.title} (${movie.pending_count}条待爬)`"
                    :value="movie.movie_id"
                  />
                </el-select>
              </el-form-item>

              <!-- 长评列表 -->
              <template v-if="taskForm.selected_movie_id">
                <el-card style="margin-bottom: 16px;">
                  <template #header>
                    <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                      <span>待爬长评列表</span>
                      <el-checkbox v-model="toggleAllCheck" @change="toggleAllReviews">
                        全选当前页
                      </el-checkbox>
                    </div>
                  </template>
                  
                  <el-table
                    :data="pendingReviews"
                    style="width: 100%"
                    v-loading="pendingReviewsLoading"
                    @selection-change="(selection: PendingReview[]) => selectedReviewIds = selection.map((s: PendingReview) => s.review_id)"
                    row-key="review_id"
                  >
                    <el-table-column type="selection" width="55" />
                    <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
                    <el-table-column prop="author" label="作者" width="120" />
                    <el-table-column prop="useful_count" label="有用" width="80" sortable />
                    <el-table-column prop="date" label="日期" width="120" />
                  </el-table>
                  
                  <el-pagination
                    v-model:current-page="pendingReviewsPage"
                    :total="pendingReviewsTotal"
                    :page-size="pendingReviewsPageSize"
                    background
                    layout="total, prev, pager, next"
                    style="margin-top: 16px; justify-content: flex-end;"
                    @current-change="fetchPendingReviews"
                  />
                </el-card>
              </template>

              <el-form-item label="Cookie 身份">
                <CookieSelector v-model="taskForm.review_cookie_id" />
                <div class="form-hint">选填，不选则使用游客模式</div>
              </el-form-item>
              <el-form-item label="代理">
        <ProxySelector v-model="taskForm.review_proxy_key" />
        <div class="form-hint">选填，不选则使用直连</div>
      </el-form-item>
            </template>

            <template v-if="taskForm.type === 'movie_scrape_task'">
              <el-form-item label="豆瓣电影 ID (douban_id)">
                <el-autocomplete
                  v-model="taskForm.scrape_douban_id"
                  :fetch-suggestions="queryClaimedIds"
                  :trigger-on-focus="true"
                  placeholder="输入搜索或选择已认领的 ID"
                  style="width: 100%"
                  clearable
                  @select="onDoubanIdSelect"
                />
                <div class="claimed-hint" v-if="claimedCount > 0">
                  🟢 已认领 {{ claimedCount }} 个豆瓣电影 ID，可在上方搜索选取
                </div>
                <div class="claimed-hint claimed-none" v-else-if="claimedCount === 0">
                  ⚠️ 暂无已认领的 ID，可手动输入或前往 <router-link to="/admin/douban-ids">豆瓣电影 ID</router-link> 认领
                </div>
              </el-form-item>
              <el-form-item label="Cookie 身份">
                <CookieSelector v-model="taskForm.scrape_cookie_id" />
                <div class="form-hint">选填，不选则使用游客模式</div>
              </el-form-item>
              <el-form-item label="代理">
                <ProxySelector v-model="taskForm.scrape_proxy_key" />
                <div class="form-hint">选填，不选则使用直连</div>
              </el-form-item>
            </template>

            <template v-if="taskForm.type === 'comment_crawl'">
              <el-form-item label="豆瓣电影 ID (douban_id)">
                <el-input v-model="taskForm.douban_id" placeholder="如 1292052" />
              </el-form-item>
              <el-form-item label="翻页数">
                <el-input-number v-model="taskForm.pages" :min="1" :max="10" style="width: 100%" />
              </el-form-item>
              <el-form-item label="Cookie 身份">
                <CookieSelector v-model="taskForm.comment_cookie_id" />
                <div class="form-hint">选填，不选则使用游客模式</div>
              </el-form-item>
              <el-form-item label="代理">
                <ProxySelector v-model="taskForm.comment_proxy_key" />
                <div class="form-hint">选填，不选则使用直连</div>
              </el-form-item>
            </template>

            <el-form-item v-if="taskForm.type">
              <el-button type="primary" @click="submitTask" :loading="submitting" :disabled="!taskForm.type">
                提交任务
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="实时队列" name="queue">
        <div class="queue-cards">
          <el-card class="q-card"><div class="q-num info">{{ queue.redis_size }}</div><div class="q-label">等待调度</div></el-card>
          <el-card class="q-card"><div class="q-num warning">{{ queue.queue_size }}</div><div class="q-label">队列待消费</div></el-card>
          <el-card class="q-card"><div class="q-num success">{{ queue.worker_busy }}</div><div class="q-label">工作中</div></el-card>
        </div>

        <div v-if="queue.in_flight?.length" class="detail-section">
          <div class="detail-section-title">🔵 执行中 ({{ queue.in_flight.length }})</div>
          <el-table :data="queue.in_flight" size="small" stripe>
            <el-table-column prop="task_id" label="任务ID" width="80" />
            <el-table-column label="类型" min-width="130">
              <template #default="{ row }"><el-tag size="small" :type="row.type === 'movie_scrape_task' ? 'warning' : 'info'">{{ typeLabel(row.type) }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="label" label="描述" min-width="160" show-overflow-tooltip />
            <el-table-column label="进度" min-width="240">
              <template #default="{ row }">
                <span class="stage-text">{{ row.stage || '执行中...' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已用" width="80">
              <template #default="{ row }">
                <span class="task-seconds">{{ liveSeconds.get(row.task_id) ?? row.busy_seconds?.toFixed(0) ?? 0 }}s</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="queue.queue_tasks?.length" class="detail-section">
          <div class="detail-section-title">🟡 队列中 ({{ queue.queue_tasks.length }})</div>
          <el-table :data="queue.queue_tasks" size="small" stripe>
            <el-table-column prop="task_id" label="任务ID" width="80" />
            <el-table-column label="类型" min-width="130">
              <template #default="{ row }"><el-tag size="small" type="warning">{{ typeLabel(row.type) }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="label" label="描述" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <div v-if="queue.redis_tasks?.length" class="detail-section">
          <div class="detail-section-title">⚪ Redis 等待 ({{ queue.redis_tasks.length }}，仅前 20)</div>
          <el-table :data="queue.redis_tasks" size="small" stripe>
            <el-table-column prop="task_id" label="任务ID" width="80" />
            <el-table-column label="类型" min-width="130">
              <template #default="{ row }"><el-tag size="small" type="info">{{ typeLabel(row.type) }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="label" label="描述" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <div v-if="!queue.in_flight?.length && !queue.queue_tasks?.length && !queue.redis_tasks?.length && !detailLoading" class="empty-hint">
          ✅ 当前无您的任务，队列空闲
        </div>
      </el-tab-pane>

      <el-tab-pane label="抓取进度" name="crawl-progress">
        <div class="toolbar">
          <el-select v-model="crawlProgressType" placeholder="全部类型" clearable style="width: 160px" @change="onCrawlProgressFilter">
            <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
          </el-select>
          <el-select v-model="crawlProgressInterval" placeholder="全部评分区间" clearable style="width: 160px; margin-left: 12px" @change="onCrawlProgressFilter">
            <el-option v-for="iv in intervalOptions" :key="iv.interval_id" :label="iv.label" :value="iv.interval_id" />
          </el-select>
        </div>

        <el-table v-if="progressList.length > 0" :data="progressList" stripe v-loading="progressLoading">
          <el-table-column prop="type_num" label="类型号" width="80" />
          <el-table-column prop="type_name" label="类型名" width="120" />
          <el-table-column label="评分阶级" width="110">
            <template #default="{ row }">
              <el-tag size="small" type="warning">{{ intervalLabel(row.interval_id) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="220">
            <template #default="{ row }">
              <div class="progress-cell">
                <el-progress
                  :percentage="row.total ? Math.round((row.crawled / row.total) * 100) : 0"
                  :stroke-width="16"
                  :color="row.done ? '#67c23a' : row.total ? '#409eff' : '#c0c4cc'"
                />
                <span class="progress-text">{{ row.crawled }} / {{ row.total || '?' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.done" type="success">✅ 已完成</el-tag>
              <el-tag v-else-if="row.total" type="warning">🔄 抓取中</el-tag>
              <el-tag v-else type="info">⏳ 未开始</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-hint">✅ 暂无抓取进度数据</div>
      </el-tab-pane>

      <el-tab-pane label="历史" name="history">
        <div class="toolbar">
          <el-select v-model="histStatus" placeholder="状态" @change="fetchHistory(1)">
            <el-option label="全部" value="" />
            <el-option label="已完成" value="done" />
            <el-option label="失败" value="failed" />
            <el-option label="执行中" value="running" />
            <el-option label="已提交" value="submitted" />
          </el-select>
        </div>
        <el-table :data="histories" stripe v-loading="histLoading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column label="任务类型" width="110">
            <template #default="{ row }">
              <el-tag size="small">{{ typeLabel(row.task_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="参数" min-width="180">
            <template #default="{ row }">
              <span class="params-text">{{ paramsSummary(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusColor(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="110" />
          <el-table-column label="操作" width="70" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="info" link @click="showHistDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination class="paginator" v-model:current-page="histPage" :total="histTotal" :page-size="histPageSize" background layout="total, prev, pager, next" @current-change="fetchHistory" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="histDetailVisible" title="任务历史详情" width="520px">
      <div v-if="histDetail" class="detail-grid">
        <div class="detail-row"><span class="detail-key">任务 ID</span><span class="detail-value">{{ histDetail.id }}</span></div>
        <div class="detail-row"><span class="detail-key">任务类型</span><el-tag size="small">{{ typeLabel(histDetail.task_type) }}</el-tag></div>
        <div class="detail-row"><span class="detail-key">状态</span><el-tag size="small" :type="statusColor(histDetail.status)">{{ statusLabel(histDetail.status) }}</el-tag></div>
        <div class="detail-row"><span class="detail-key">创建时间</span><span class="detail-value">{{ histDetail.created_at }}</span></div>
        <div class="detail-row"><span class="detail-key">更新时间</span><span class="detail-value">{{ histDetail.updated_at }}</span></div>
        <div class="detail-row" v-if="histDetail.message">
          <span class="detail-key">消息</span><span class="detail-value detail-mono">{{ histDetail.message }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">参数</span>
          <code class="detail-params">{{ JSON.stringify(histDetail.task_params, null, 2) }}</code>
        </div>
        <template v-if="histDetail.related_failure">
          <el-divider />
          <p class="detail-section-title">📛 关联失败记录</p>
          <div class="detail-row"><span class="detail-key">失败 ID</span><span class="detail-value">{{ histDetail.related_failure.failure_id }}</span></div>
          <div class="detail-row"><span class="detail-key">原因</span><span class="detail-value detail-mono">{{ histDetail.related_failure.reason }}</span></div>
          <div class="detail-row"><span class="detail-key">状态</span><el-tag size="small" :type="histDetail.related_failure.status === 'resolved' ? 'success' : 'warning'">{{ histDetail.related_failure.status }}</el-tag></div>
          <div class="detail-row"><span class="detail-key">重试次数</span><span class="detail-value">{{ histDetail.related_failure.retry_count }}</span></div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminTasksApi, adminTaskHistoryApi, type TaskHistory, type TaskHistoryDetail } from '@/api/admin/tasks'
import { adminQueueApi } from '@/api/admin/monitor'
import { adminDoubanIdsApi } from '@/api/admin/douban_ids'
import { adminCookieApi, type CookieAccount } from '@/api/admin/infra'
import { adminMoviesApi } from '@/api/admin/movies'
import ProxySelector from '@/components/common/ProxySelector.vue'
import CookieSelector from '@/components/common/CookieSelector.vue'
import type { QueueStatus } from '@/types/status'
import type { MovieWithPendingReviews, PendingReview, TaskSubmitResponse } from '@/types/task'

const authStore = useAuthStore()

const TYPE_MAP: Record<number, string> = {
  1: '纪录片', 2: '传记', 3: '犯罪', 4: '历史', 5: '动作',
  6: '情色', 7: '歌舞', 8: '儿童', 10: '悬疑', 11: '剧情',
  12: '灾难', 13: '爱情', 14: '音乐', 15: '冒险', 16: '奇幻',
  17: '科幻', 18: '运动', 19: '惊悚', 20: '恐怖', 22: '战争',
  23: '短片', 24: '喜剧', 25: '动画', 27: '西部', 28: '家庭',
  29: '武侠', 30: '古装', 31: '黑色电影',
}

const typeOptions: { type_num: number; type_name: string }[] = Object.entries(TYPE_MAP).map(
  ([num, name]) => ({ type_num: Number(num), type_name: name })
)

const intervalOptions = [
  { interval_id: '100:90', label: '9.0~10.0' },
  { interval_id: '90:80', label: '8.0~9.0' },
  { interval_id: '80:70', label: '7.0~8.0' },
  { interval_id: '70:60', label: '6.0~7.0' },
  { interval_id: '60:50', label: '5.0~6.0' },
  { interval_id: '50:40', label: '4.0~5.0' },
  { interval_id: '40:30', label: '3.0~4.0' },
  { interval_id: '30:20', label: '2.0~3.0' },
  { interval_id: '20:10', label: '1.0~2.0' },
  { interval_id: '10:0', label: '0~1.0' },
]

const activeTab = ref('submit')
const submitting = ref(false)
const crawlProgressType = ref<number | undefined>(undefined)
const crawlProgressInterval = ref('')
const histStatus = ref('')

const taskForm = reactive({ 
  type: '',
  type_num: 11,
  interval_id: '100:90',
  douban_id: '',
  pages: 2, // comment_crawl 保留翻页参数
  scrape_douban_id: '',
  scrape_cookie_id: '',
  scrape_proxy_key: '',
  // 新增字段
  review_cookie_id: '',
  review_proxy_key: '',
  comment_cookie_id: '',
  comment_proxy_key: '',
  // 批量长评相关
  selected_movie_id: null as number | null,
})

// 批量长评相关状态
const moviesWithPendingReviews = ref<MovieWithPendingReviews[]>([])
const moviesLoading = ref(false)
const pendingReviews = ref<PendingReview[]>([])
const pendingReviewsLoading = ref(false)
const selectedReviewIds = ref<string[]>([])
const pendingReviewsPage = ref(1)
const pendingReviewsTotal = ref(0)
const pendingReviewsPageSize = 10

const queue = reactive<QueueStatus>({
  redis_size: 0,
  queue_size: 0,
  worker_busy: 0,
  worker_idle: 0,
  in_flight: [],
  queue_tasks: [],
  redis_tasks: [],
})
const detailLoading = ref(false)
const progressList = ref<Array<Record<string, unknown>>>([])
const progressLoading = ref(false)

const histories = ref<TaskHistory[]>([])
const histPage = ref(1)
const histTotal = ref(0)
const histPageSize = ref(20)
const histLoading = ref(false)
const histDetail = ref<TaskHistoryDetail | null>(null)
const histDetailVisible = ref(false)
const claimedCount = ref(-1)

/* ── 执行中任务秒数实时递增 ── */
const liveSeconds = reactive(new Map<number, number>())
const _taskStartRefs = new Map<number, number>()
let _secondsTimer: ReturnType<typeof setInterval> | null = null

function _sanitizeBusy(value: number | undefined): number {
  if (value == null) return 0
  if (value > 1_000_000) return 0
  return value
}

function syncLiveSeconds(): void {
  if (!queue.in_flight) return
  for (const t of queue.in_flight) {
    const sanitized = _sanitizeBusy(t.busy_seconds)
    const prev = liveSeconds.get(t.task_id)
    if (prev === undefined) {
      _taskStartRefs.set(t.task_id, Date.now() - Math.round(sanitized * 1000))
    }
    liveSeconds.set(t.task_id, sanitized)
  }
  for (const key of liveSeconds.keys()) {
    if (!queue.in_flight.some(t => t.task_id === key)) {
      liveSeconds.delete(key)
      _taskStartRefs.delete(key)
    }
  }
}

function startSecondsTimer(): void {
  stopSecondsTimer()
  _secondsTimer = setInterval(() => {
    const now = Date.now()
    for (const [taskId] of liveSeconds) {
      const start = _taskStartRefs.get(taskId) || now
      liveSeconds.set(taskId, Math.round((now - start) / 100) / 10)
    }
  }, 500)
}

function stopSecondsTimer(): void {
  if (_secondsTimer) {
    clearInterval(_secondsTimer)
    _secondsTimer = null
  }
}

/* ── Cookie 账号下拉 ── */
const cookieAccounts = ref<CookieAccount[]>([])
const cookieLoadingOptions = ref(false)



async function fetchCookieOptions() {
  cookieLoadingOptions.value = true
  try {
    const res = await adminCookieApi.list()
    cookieAccounts.value = res.data.items?.filter(a => a.state !== 'banned') || []
  } catch {
    cookieAccounts.value = []
  } finally {
    cookieLoadingOptions.value = false
  }
}

function onCookieDropdownOpen(visible: boolean) {
  if (visible && cookieAccounts.value.length === 0) {
    fetchCookieOptions()
  }
}

function stateType(state: string): string {
  const m: Record<string, string> = { active: 'success', suspicious: 'warning', banned: 'danger' }
  return m[state] || 'info'
}

function stateLabel(state: string): string {
  const m: Record<string, string> = { active: '活跃', suspicious: '可疑', banned: '封禁' }
  return m[state] || state
}

function intervalLabel(intervalId: string): string {
  const found = intervalOptions.find(iv => iv.interval_id === intervalId)
  return found?.label || intervalId || '—'
}

function onCrawlProgressFilter() {
  fetchProgress()
}

async function fetchQueue() {
  try {
    const adminId = authStore.user?.id
    const res = await adminQueueApi.get(adminId ? { admin_id: adminId } : {})
    Object.assign(queue, res.data)
  } catch { /* ignore */ }
}

async function fetchProgress() {
  progressLoading.value = true
  try {
    const params: { type_num?: number; interval_id?: string; page_size: number } = { page_size: 100 }
    if (crawlProgressType.value) params.type_num = crawlProgressType.value
    if (crawlProgressInterval.value) params.interval_id = crawlProgressInterval.value
    const res = await adminTasksApi.list(params)
    progressList.value = (res.data.items || [])
      .filter((r: any) => r.douban_total > 0)
      .map((r: any) => ({
        ...r,
        total: r.douban_total,
        crawled: r.crawled_count,
        done: r.crawled_count >= r.douban_total,
      }))
  } catch { /* ignore */ } finally { progressLoading.value = false }
}

async function fetchProgressDetail() {
  detailLoading.value = true
  try {
    const adminId = authStore.user?.id
    const res = await adminQueueApi.fetchDetails(adminId)
    Object.assign(queue, res.data)
    syncLiveSeconds()
    if (queue.in_flight?.length) {
      startSecondsTimer()
    } else {
      stopSecondsTimer()
    }
  } catch { /* ignore */ } finally { detailLoading.value = false }
}

async function fetchHistory(p = 1) {
  histLoading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: histPageSize.value }
    if (histStatus.value) params.status = histStatus.value
    const res = await adminTaskHistoryApi.list(params as any)
    histories.value = res.data.items
    histTotal.value = res.data.total
    histPage.value = p
  } catch { /* ignore */ } finally { histLoading.value = false }
}

function onTabChange(tab: string) {
  if (tab === 'queue') {
    fetchProgressDetail()
  } else if (tab === 'crawl-progress') {
    fetchProgress()
    stopSecondsTimer()
  } else {
    stopSecondsTimer()
  }
}

function onTypeChange() {
  // 重置所有公共字段
  taskForm.douban_id = ''
  taskForm.pages = 2
  // 重置movie_scrape_task字段
  taskForm.scrape_douban_id = ''
  taskForm.scrape_cookie_id = ''
  taskForm.scrape_proxy_key = ''
  // 重置review_crawl字段
  taskForm.review_cookie_id = ''
  taskForm.review_proxy_key = ''
  // 重置comment_crawl字段
  taskForm.comment_cookie_id = ''
  taskForm.comment_proxy_key = ''
  // 重置批量长评相关
  taskForm.selected_movie_id = null
  selectedReviewIds.value = []
  pendingReviews.value = []
  
  // 加载Cookie选项
  if (['movie_scrape_task', 'review_crawl', 'comment_crawl', 'review_body_crawl'].includes(taskForm.type)) {
    fetchCookieOptions()
  }
  
  // 如果是review_body_crawl，加载待爬电影列表
  if (taskForm.type === 'review_body_crawl') {
    fetchMoviesWithPendingReviews()
  }
}

async function queryClaimedIds(query: string, cb: (items: { value: string; label: string }[]) => void) {
  try {
    const res = await adminDoubanIdsApi.list({ is_acquired: '1', keyword: query || '', page_size: 20 })
    const items = (res.data.items || []).map(item => ({
      value: item.douban_id,
      label: `${item.douban_id}  ${item.title}`,
    }))
    cb(items)
  } catch {
    cb([])
  }
}

async function fetchClaimedCount() {
  claimedCount.value = -1
  try {
    const res = await adminDoubanIdsApi.list({ is_acquired: '1', page_size: 1 })
    claimedCount.value = res.data.total
  } catch {
    claimedCount.value = -1
  }
}

function onDoubanIdSelect(item: { value: string; label: string }) {
  taskForm.scrape_douban_id = item.value
}

// 批量长评相关函数
async function fetchMoviesWithPendingReviews() {
  moviesLoading.value = true
  try {
    const res = await adminMoviesApi.getMoviesWithPendingReviews()
    moviesWithPendingReviews.value = res.data.items || []
  } catch {
    ElMessage.error('获取待爬电影列表失败')
  } finally {
    moviesLoading.value = false
  }
}

async function fetchPendingReviews(page = 1) {
  if (!taskForm.selected_movie_id) return
  
  pendingReviewsLoading.value = true
  try {
    const res = await adminMoviesApi.getPendingReviews(
      taskForm.selected_movie_id,
      { page, page_size: pendingReviewsPageSize }
    )
    pendingReviews.value = res.data.items || []
    pendingReviewsTotal.value = res.data.total
    pendingReviewsPage.value = res.data.page
  } catch {
    ElMessage.error('获取待爬长评列表失败')
  } finally {
    pendingReviewsLoading.value = false
  }
}

function onMovieSelect() {
  // 清空已选中的评论
  selectedReviewIds.value = []
  if (taskForm.selected_movie_id) {
    fetchPendingReviews(1)
  }
}

function toggleAllReviews() {
  if (selectedReviewIds.value.length === pendingReviews.value.length) {
    // 取消全选
    selectedReviewIds.value = []
  } else {
    // 全选当前页
    selectedReviewIds.value = pendingReviews.value.map(r => r.review_id)
  }
}

// 获取选中电影的douban_id
const selectedMovie = computed(() => {
  return moviesWithPendingReviews.value.find(m => m.movie_id === taskForm.selected_movie_id)
})

// 全选checkbox的状态
const toggleAllCheck = computed({
  get: () => pendingReviews.value.length > 0 && 
    selectedReviewIds.value.length === pendingReviews.value.length,
  set: () => {}
})

async function submitTask() {
  if (taskForm.type === 'review_body_crawl' && selectedReviewIds.value.length > 0) {
    // 批量提交模式
    await submitBatchReviewBodyTasks()
    return
  }

  // 原有的单个任务提交模式
  submitting.value = true
  try {
    const payload: any = { type: taskForm.type }
    switch (taskForm.type) {
      case 'movie_crawl':
        payload.type_num = taskForm.type_num
        payload.interval_id = taskForm.interval_id
        break
      case 'review_crawl':
        payload.douban_id = taskForm.douban_id
        payload.pages = taskForm.pages
        if (taskForm.review_cookie_id) payload.cookie_id = taskForm.review_cookie_id
        if (taskForm.review_proxy_key) payload.proxy_key = taskForm.review_proxy_key
        break
      case 'comment_crawl':
        payload.douban_id = taskForm.douban_id
        payload.pages = taskForm.pages
        if (taskForm.comment_cookie_id) payload.cookie_id = taskForm.comment_cookie_id
        if (taskForm.comment_proxy_key) payload.proxy_key = taskForm.comment_proxy_key
        break
      case 'review_body_crawl':
        payload.douban_id = taskForm.douban_id
        if (taskForm.review_cookie_id) payload.cookie_id = taskForm.review_cookie_id
        if (taskForm.review_proxy_key) payload.proxy_key = taskForm.review_proxy_key
        break
      case 'movie_scrape_task':
        payload.douban_id = taskForm.scrape_douban_id
        if (taskForm.scrape_cookie_id) payload.cookie_id = taskForm.scrape_cookie_id
        if (taskForm.scrape_proxy_key) payload.proxy_key = taskForm.scrape_proxy_key
        break
    }
    await adminTasksApi.submit(payload)
    ElMessage.success(`任务已提交 (${taskForm.type})`)
    await fetchQueue()
    await fetchProgress()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '提交失败')
  } finally { submitting.value = false }
}

async function submitBatchReviewBodyTasks() {
  if (!selectedMovie.value) {
    ElMessage.error('请先选择电影')
    return
  }
  
  if (selectedReviewIds.value.length === 0) {
    ElMessage.error('请先选择要爬取的长评')
    return
  }

  submitting.value = true
  let successCount = 0
  let skipCount = 0
  const skipReasons: string[] = []

  try {
    const doubanId = selectedMovie.value.douban_id || taskForm.douban_id
    
    for (const reviewId of selectedReviewIds.value) {
      const review = pendingReviews.value.find(r => r.review_id === reviewId)
      if (!review) continue

      const payload: any = {
        type: 'review_body_crawl',
        douban_id: doubanId,
        review_id: review.review_id,
        title: review.title,
        author: review.author,
      }
      if (taskForm.review_cookie_id) payload.cookie_id = taskForm.review_cookie_id
      if (taskForm.review_proxy_key) payload.proxy_key = taskForm.review_proxy_key

      try {
        const res = await adminTasksApi.submit(payload)
        if (res.data.skipped) {
          skipCount++
          skipReasons.push(`${reviewId}: ${res.data.reason || '已忽略'}`)
        } else {
          successCount++
        }
      } catch (e) {
        skipCount++
        skipReasons.push(`${reviewId}: 提交失败`)
      }
    }

    let message = `批量提交完成：成功 ${successCount} 条`
    if (skipCount > 0) {
      message += `，跳过 ${skipCount} 条`
    }

    ElMessage.success(message)

    if (skipReasons.length > 0) {
      console.log('跳过详情：', skipReasons)
    }

    await fetchQueue()
    await fetchProgress()
    // 刷新待爬列表
    fetchPendingReviews(pendingReviewsPage.value)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '批量提交失败')
  } finally {
    submitting.value = false
  }
}

function typeLabel(t: string) { const m: Record<string, string> = { movie_crawl: '电影抓取', movie_scrape_task: '详情爬取', review_crawl: '长评列表', review_body_crawl: '长评正文', comment_crawl: '短评抓取', director_crawl: '参演职员爬取' }; return m[t] || t }
function statusLabel(s: string) { const m: Record<string, string> = { submitted: '已提交', running: '执行中', done: '已完成', failed: '失败' }; return m[s] || s }
function statusColor(s: string) { const m: Record<string, string> = { submitted: 'info', running: 'warning', done: 'success', failed: 'danger' }; return m[s] || 'info' }
function paramsSummary(row: any) {
  const params = row.task_params || {}
  if (row.task_type === 'movie_crawl') {
    const typeName = TYPE_MAP[params.type_num] || params.type_num
    return `${typeName} | ${params.interval_id}`
  } else if (row.task_type === 'review_crawl' || row.task_type === 'comment_crawl') {
    const parts: string[] = []
    if (params.douban_id) parts.push(`douban_id: ${params.douban_id}`)
    if (params.pages) parts.push(`${params.pages}页`)
    if (params.cookie_id) parts.push(`cookie: ${params.cookie_id}`)
    if (params.proxy_key) parts.push(`proxy: ${params.proxy_key}`)
    return parts.join(' | ')
  } else if (row.task_type === 'review_body_crawl') {
    const parts: string[] = []
    if (params.douban_id) parts.push(`douban_id: ${params.douban_id}`)
    if (params.cookie_id) parts.push(`cookie: ${params.cookie_id}`)
    if (params.proxy_key) parts.push(`proxy: ${params.proxy_key}`)
    return parts.join(' | ')
  } else if (row.task_type === 'movie_scrape_task' || row.task_type === 'director_crawl' || row.task_type === 'movie_detail_crawl') {
    const parts: string[] = []
    if (params.douban_id) parts.push(`douban_id: ${params.douban_id}`)
    if (params.cookie_id) parts.push(`cookie: ${params.cookie_id}`)
    if (params.proxy_key) parts.push(`proxy: ${params.proxy_key}`)
    return parts.join(' | ')
  }
  return ''
}

async function showHistDetail(row: TaskHistory) {
  histDetailVisible.value = true
  histDetail.value = null
  try {
    const res = await adminTaskHistoryApi.detail(row.id)
    histDetail.value = res.data
  } catch { /* ignore */ }
}

onMounted(() => { fetchQueue(); fetchProgress(); fetchHistory() })

onUnmounted(() => { stopSecondsTimer() })
</script>

<style scoped>
.crawler-page { max-width: 1100px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.task-card { border-radius: 8px; }
.queue-cards { display: flex; gap: 16px; margin-bottom: 16px; }
.q-card { flex: 1; text-align: center; border-radius: 8px; }
.q-num { font-size: 32px; font-weight: 700; }
.q-num.info { color: #409eff; }
.q-num.warning { color: #e6a23c; }
.q-num.success { color: #67c23a; }
.q-label { font-size: 13px; color: #888; margin-top: 4px; }
.progress-cell { display: flex; align-items: center; gap: 10px; }
.progress-cell .el-progress { flex: 1; }
.progress-text { font-size: 13px; color: #555; white-space: nowrap; }
.toolbar { margin-bottom: 12px; }
.params-text { font-size: 13px; color: #555; }
.paginator { margin-top: 16px; justify-content: flex-end; }
.detail-grid { display: flex; flex-direction: column; gap: 10px; }
.detail-row { display: flex; align-items: flex-start; gap: 12px; }
.detail-key { font-size: 13px; color: #909399; min-width: 80px; text-align: right; flex-shrink: 0; }
.detail-value { font-size: 14px; color: #303133; word-break: break-all; }
.detail-mono { font-family: monospace; font-size: 13px; }
.detail-params { display: block; background: #f5f7fa; border-radius: 4px; padding: 8px 12px; font-size: 12px; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
.detail-section { margin-bottom: 12px; }
.detail-section .detail-section-title { font-size: 13px; color: #606266; font-weight: 600; margin: 0 0 6px; }
.stage-text { font-size: 12px; color: #606266; }
.task-seconds { font-size: 13px; color: #e6a23c; font-weight: 600; }
.empty-hint { text-align: center; color: #909399; font-size: 14px; padding: 24px 0; }
.claimed-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.claimed-hint.claimed-none { color: #e6a23c; }
.claimed-hint a { color: #409eff; }
.form-hint { font-size: 12px; color: #909399; margin-top: 2px; }
.c-gray { color: #909399; font-size: 12px; }
.region-tag { margin-left: 4px; }
.state-tag { margin-left: 4px; }
</style>
