<template>
  <div class="admin-reviews">
    <h2 class="page-title">评论管理</h2>

    <div class="filter-section">
      <div class="filter-label">电影筛选</div>
      <div class="filter-row">
        <el-select
          v-model="movieIdFilter"
          placeholder="全部电影"
          clearable
          filterable
          remote
          remote-show-suffix
          :remote-method="searchMovies"
          :loading="movieOptionsLoading"
          class="filter-select"
          style="width: 280px"
        >
          <el-option v-for="m in movieOptions" :key="m.movie_id" :label="m.title" :value="m.movie_id" />
        </el-select>
        <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select" style="width: 140px">
          <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
        </el-select>
        <el-input v-model="yearFilter" placeholder="年份" clearable class="year-input" maxlength="4" @blur="onYearFilterChange" @keyup.enter="onYearFilterChange" />
        <el-select v-model="regionFilter" placeholder="全部国家/地区" clearable class="filter-select" style="width: 150px">
          <el-option v-for="r in allRegions" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-select v-model="ratingFilter" placeholder="全部评分" clearable class="filter-select" style="width: 130px">
          <el-option label="9分及以上" value="100:90" />
          <el-option label="8-9分" value="90:80" />
          <el-option label="7-8分" value="80:70" />
          <el-option label="6-7分" value="70:60" />
          <el-option label="6分以下" value="60:0" />
        </el-select>
      </div>
    </div>

    <div class="filter-section">
      <div class="filter-label">评论筛选</div>
      <div class="filter-row">
        <el-select v-model="publishedFilter" placeholder="上架状态" clearable class="filter-select" style="width: 130px">
          <el-option label="已上架" value="published" />
          <el-option label="已下架" value="unpublished" />
          <el-option label="用户删除" value="removed" />
        </el-select>
      </div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="长评" name="reviews">
        <el-table :data="reviews" stripe v-loading="revLoading">
          <el-table-column prop="review_id" label="ID" width="90" />
          <el-table-column prop="movie_title" label="所属电影" width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.movie_title">{{ row.movie_title }}</span>
              <span v-else>ID: {{ row.movie_id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="author" label="作者" width="120" />
          <el-table-column prop="text" label="内容" min-width="320">
            <template #default="{ row }">
              <div class="table-content-preview">
                {{ row.text?.slice(0, 50) }}{{ row.text?.length > 50 ? '...' : '' }}
              </div>
              <el-button
                v-if="row.text?.length > 50"
                type="primary"
                link
                size="small"
                @click="showReviewDetail(row)"
              >
                查看全文
              </el-button>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.removed_by === 'user'" type="danger" size="small">用户已删除</el-tag>
              <el-tag v-else :type="(row.is_published ?? !row.removed_by) ? 'success' : 'info'" size="small">{{ (row.is_published ?? !row.removed_by) ? '已上架' : '已下架' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-tooltip v-if="row.removed_by === 'user'" content="该评论已被用户主动删除，无法重新上架" placement="top">
                <el-button size="small" type="success" link disabled>上架</el-button>
              </el-tooltip>
              <el-button v-else-if="authStore.checkPermission('comment:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="toggleReviewPublish(row)">
                {{ row.is_published ? '下架' : '上架' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="revPage" :total="revTotal" :page-size="15" background layout="total, prev, pager, next" class="paginator" @current-change="fetchReviews" />
      </el-tab-pane>

      <el-tab-pane label="短评" name="comments">
        <el-table :data="comments" stripe v-loading="comLoading">
          <el-table-column prop="comment_id" label="ID" width="90" />
          <el-table-column prop="movie_title" label="所属电影" width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.movie_title">{{ row.movie_title }}</span>
              <span v-else>ID: {{ row.movie_id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="author" label="作者" width="120" />
          <el-table-column prop="text" label="内容" min-width="320">
            <template #default="{ row }">
              <div class="table-content-preview">
                {{ row.text?.slice(0, 50) }}{{ row.text?.length > 50 ? '...' : '' }}
              </div>
              <el-button
                v-if="row.text?.length > 50"
                type="primary"
                link
                size="small"
                @click="showCommentDetail(row)"
              >
                查看全文
              </el-button>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.removed_by === 'user'" type="danger" size="small">用户已删除</el-tag>
              <el-tag v-else :type="(row.is_published ?? !row.removed_by) ? 'success' : 'info'" size="small">{{ (row.is_published ?? !row.removed_by) ? '已上架' : '已下架' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-tooltip v-if="row.removed_by === 'user'" content="该评论已被用户主动删除，无法重新上架" placement="top">
                <el-button size="small" type="success" link disabled>上架</el-button>
              </el-tooltip>
              <el-button v-else-if="authStore.checkPermission('comment:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="toggleCommentPublish(row)">
                {{ row.is_published ? '下架' : '上架' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="comPage" :total="comTotal" :page-size="15" background layout="total, prev, pager, next" class="paginator" @current-change="fetchComments" />
      </el-tab-pane>
    </el-tabs>

    <!-- 长评详情弹窗 -->
    <el-dialog
      v-model="reviewDetailVisible"
      title="长评详情"
      width="600px"
    >
      <div class="detail-content">
        <div class="detail-meta">
          <p><strong>电影：</strong>{{ currentReview?.movie_title || `ID: ${currentReview?.movie_id}` }}</p>
          <p><strong>作者：</strong>{{ currentReview?.author }}</p>
        </div>
        <div class="detail-text" v-html="formatContent(currentReview?.text)"></div>
      </div>
    </el-dialog>

    <!-- 短评详情弹窗 -->
    <el-dialog
      v-model="commentDetailVisible"
      title="短评详情"
      width="600px"
    >
      <div class="detail-content">
        <div class="detail-meta">
          <p><strong>电影：</strong>{{ currentComment?.movie_title || `ID: ${currentComment?.movie_id}` }}</p>
          <p><strong>作者：</strong>{{ currentComment?.author }}</p>
        </div>
        <div class="detail-text" v-html="formatContent(currentComment?.text)"></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminReviewsApi, type AdminReview, type AdminComment } from '@/api/admin/reviews'
import client from '@/api/client'

const authStore = useAuthStore()
const route = useRoute()

const queryTab = route.query.tab as string | undefined
const queryMovieId = route.query.movie_id ? Number(route.query.movie_id) : undefined

const activeTab = ref(queryTab && ['reviews', 'comments'].includes(queryTab) ? queryTab : 'reviews')

const TYPE_MAP: Record<number, string> = {
  1: '纪录片', 2: '传记', 3: '犯罪', 4: '历史', 5: '动作',
  6: '情色', 7: '歌舞', 8: '儿童', 10: '悬疑', 11: '剧情',
  12: '灾难', 13: '爱情', 14: '音乐', 15: '冒险', 16: '奇幻',
  17: '科幻', 18: '运动', 19: '惊悚', 20: '恐怖', 22: '战争',
  23: '短片', 24: '喜剧', 25: '动画', 27: '西部', 28: '家庭',
  29: '武侠', 30: '古装', 31: '黑色电影',
}

const typeOptions = Object.entries(TYPE_MAP).map(
  ([num, name]) => ({ type_num: Number(num), type_name: name })
)

const allRegions = ref<{ id: number; name: string }[]>([])

// 电影下拉筛选
const movieIdFilter = ref<number | undefined>(queryMovieId)
const typeFilter = ref<number | undefined>(undefined)
const yearFilter = ref('')
const regionFilter = ref<number | undefined>(undefined)
const ratingFilter = ref('')
const publishedFilter = ref<string | undefined>()
const movieOptions = ref<{ movie_id: number; title: string }[]>([])
const movieOptionsLoading = ref(false)
let movieSearchTimer: ReturnType<typeof setTimeout> | null = null

const reviews = ref<AdminReview[]>([])
const revPage = ref(1)
const revTotal = ref(0)
const revLoading = ref(false)

const comments = ref<AdminComment[]>([])
const comPage = ref(1)
const comTotal = ref(0)
const comLoading = ref(false)

// 详情弹窗相关
const reviewDetailVisible = ref(false)
const commentDetailVisible = ref(false)
const currentReview = ref<AdminReview | null>(null)
const currentComment = ref<AdminComment | null>(null)

async function fetchAllRegions() {
  try {
    const res = await client.get<{ id: number; name: string }[]>('/admin/regions')
    allRegions.value = res.data || []
  } catch { /* ignore */ }
}

// 加载电影选项列表（下拉数据源）
async function fetchMovieOptions(keyword = '') {
  movieOptionsLoading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (keyword) params.keyword = keyword
    const res = await adminReviewsApi.reviewMovies(params as any)
    movieOptions.value = res.data.items || []
  } catch { /* ignore */ } finally {
    movieOptionsLoading.value = false
  }
}

// 远程搜索电影（防抖300ms）
function searchMovies(query: string) {
  if (movieSearchTimer) clearTimeout(movieSearchTimer)
  movieSearchTimer = setTimeout(() => fetchMovieOptions(query.trim()), 300)
}

// 年份筛选：失焦/回车时触发查询
function onYearFilterChange() {
  fetchReviews(1)
  fetchComments(1)
}

// 监听筛选变化，刷新评论列表
watch([movieIdFilter, typeFilter, regionFilter, publishedFilter, ratingFilter], () => {
  fetchReviews(1)
  fetchComments(1)
})

async function fetchReviews(p = 1) {
  revLoading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: 15 }
    if (movieIdFilter.value) params.movie_id = movieIdFilter.value
    if (typeFilter.value) params.type_num = typeFilter.value
    if (yearFilter.value) {
      const y = parseInt(yearFilter.value, 10)
      if (!isNaN(y)) params.release_year = y
    }
    if (regionFilter.value !== undefined) params.region_id = regionFilter.value
    if (ratingFilter.value) params.interval_ids = ratingFilter.value
    if (publishedFilter.value) params.published = publishedFilter.value === 'published' ? 1 : publishedFilter.value === 'unpublished' ? 0 : -1
    const res = await adminReviewsApi.reviews(params as any)
    reviews.value = res.data.items
    revTotal.value = res.data.total
    revPage.value = p
  } catch { /* ignore */ } finally { revLoading.value = false }
}

async function fetchComments(p = 1) {
  comLoading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: 15 }
    if (movieIdFilter.value) params.movie_id = movieIdFilter.value
    if (typeFilter.value) params.type_num = typeFilter.value
    if (yearFilter.value) {
      const y = parseInt(yearFilter.value, 10)
      if (!isNaN(y)) params.release_year = y
    }
    if (regionFilter.value !== undefined) params.region_id = regionFilter.value
    if (ratingFilter.value) params.interval_ids = ratingFilter.value
    if (publishedFilter.value) params.published = publishedFilter.value === 'published' ? 1 : publishedFilter.value === 'unpublished' ? 0 : -1
    const res = await adminReviewsApi.comments(params as any)
    comments.value = res.data.items
    comTotal.value = res.data.total
    comPage.value = p
  } catch { /* ignore */ } finally { comLoading.value = false }
}

function onTabChange() {
  // 切tab时如果有电影筛选就不用管，否则正常
}

async function toggleReviewPublish(row: AdminReview) {
  try {
    const api = row.is_published ? adminReviewsApi.unpublishReview : adminReviewsApi.publishReview
    await api(row.review_id)
    ElMessage.success(row.is_published ? '已下架' : '已上架')
    await fetchReviews(revPage.value)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.error || '操作失败')
  }
}

async function toggleCommentPublish(row: AdminComment) {
  try {
    const api = row.is_published ? adminReviewsApi.unpublishComment : adminReviewsApi.publishComment
    await api(row.comment_id)
    ElMessage.success(row.is_published ? '已下架' : '已上架')
    await fetchComments(comPage.value)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.error || '操作失败')
  }
}

function formatContent(content: string | undefined): string {
  if (!content) return ''
  return content.replace(/\n/g, '<br>')
}

function showReviewDetail(row: AdminReview) {
  currentReview.value = row
  reviewDetailVisible.value = true
}

function showCommentDetail(row: AdminComment) {
  currentComment.value = row
  commentDetailVisible.value = true
}

onMounted(async () => {
  await fetchAllRegions()
  await fetchMovieOptions()
  fetchReviews()
  fetchComments()
})
</script>

<style scoped>
.admin-reviews { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.filter-section { margin-bottom: 14px; }
.filter-label { font-size: 13px; color: #909399; margin-bottom: 6px; }
.filter-row { display: flex; gap: 12px; flex-wrap: wrap; }
.filter-select { width: 120px; }
.year-input { width: 100px; }
.paginator { margin-top: 16px; justify-content: flex-end; }

.table-content-preview {
  font-size: 14px;
  color: #606266;
  line-height: 1.5;
}

.detail-content {
  font-size: 14px;
}

.detail-meta {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e8e8e8;
}

.detail-meta p {
  margin: 8px 0;
  color: #606266;
}

.detail-text {
  max-height: 400px;
  overflow-y: auto;
  line-height: 1.8;
  color: #303133;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 4px;
}
</style>
