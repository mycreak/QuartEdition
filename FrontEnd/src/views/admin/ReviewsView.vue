<template>
  <div class="admin-reviews">
    <h2 class="page-title">评论管理</h2>

    <div class="toolbar">
      <el-select
        v-model="movieIdFilter"
        placeholder="全部电影"
        clearable
        filterable
        remote
        remote-show-suffix
        :remote-method="searchMovies"
        :loading="movieOptionsLoading"
        class="movie-filter"
      >
        <el-option v-for="m in movieOptions" :key="m.movie_id" :label="m.title" :value="m.movie_id" />
      </el-select>
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
          <el-table-column prop="text" label="内容" min-width="320" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_published ? 'success' : 'info'" size="small">{{ row.is_published ? '已上架' : '已下架' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button v-if="authStore.checkPermission('comment:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="toggleReviewPublish(row)">
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
          <el-table-column prop="text" label="内容" min-width="320" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_published ? 'success' : 'info'" size="small">{{ row.is_published ? '已上架' : '已下架' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button v-if="authStore.checkPermission('comment:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="toggleCommentPublish(row)">
                {{ row.is_published ? '下架' : '上架' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="comPage" :total="comTotal" :page-size="15" background layout="total, prev, pager, next" class="paginator" @current-change="fetchComments" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminReviewsApi, type AdminReview, type AdminComment } from '@/api/admin/reviews'

const authStore = useAuthStore()
const route = useRoute()

const queryTab = route.query.tab as string | undefined
const queryMovieId = route.query.movie_id ? Number(route.query.movie_id) : undefined

const activeTab = ref(queryTab && ['reviews', 'comments'].includes(queryTab) ? queryTab : 'reviews')

// 电影下拉筛选
const movieIdFilter = ref<number | undefined>(queryMovieId)
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

// 监听电影筛选变化，刷新评论列表
watch(movieIdFilter, () => {
  fetchReviews(1)
  fetchComments(1)
})

async function fetchReviews(p = 1) {
  revLoading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: 15 }
    if (movieIdFilter.value) params.movie_id = movieIdFilter.value
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
    row.is_published = !row.is_published
    ElMessage.success(row.is_published ? '已上架' : '已下架')
  } catch { ElMessage.error('操作失败') }
}

async function toggleCommentPublish(row: AdminComment) {
  try {
    const api = row.is_published ? adminReviewsApi.unpublishComment : adminReviewsApi.publishComment
    await api(row.comment_id)
    row.is_published = !row.is_published
    ElMessage.success(row.is_published ? '已上架' : '已下架')
  } catch { ElMessage.error('操作失败') }
}

onMounted(async () => {
  await fetchMovieOptions()
  fetchReviews()
  fetchComments()
})
</script>

<style scoped>
.admin-reviews { max-width: 1100px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.movie-filter { width: 280px; }
.rating-cell { color: #e8a838; font-weight: 600; }
.paginator { margin-top: 16px; justify-content: flex-end; }
</style>
