<template>
  <div class="admin-reviews">
    <h2 class="page-title">评论管理</h2>

    <div class="filter-bar" v-if="queryMovieId">
      <el-tag closable type="info" @close="clearMovieFilter">
        仅显示电影 #{{ queryMovieId }} 的评论
      </el-tag>
    </div>

    <el-tabs v-model="activeTab">
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
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminReviewsApi, type AdminReview, type AdminComment } from '@/api/admin/reviews'

const authStore = useAuthStore()
const route = useRoute()

const queryTab = route.query.tab as string | undefined
const queryMovieId = route.query.movie_id ? Number(route.query.movie_id) : undefined

const activeTab = ref(queryTab && ['reviews', 'comments'].includes(queryTab) ? queryTab : 'reviews')

const reviews = ref<AdminReview[]>([])
const revPage = ref(1)
const revTotal = ref(0)
const revLoading = ref(false)

const comments = ref<AdminComment[]>([])
const comPage = ref(1)
const comTotal = ref(0)
const comLoading = ref(false)

async function fetchReviews(p = 1) {
  revLoading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: 15 }
    if (queryMovieId) params.movie_id = queryMovieId
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
    if (queryMovieId) params.movie_id = queryMovieId
    const res = await adminReviewsApi.comments(params as any)
    comments.value = res.data.items
    comTotal.value = res.data.total
    comPage.value = p
  } catch { /* ignore */ } finally { comLoading.value = false }
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

function clearMovieFilter() {
  const url = new URL(window.location.href)
  url.searchParams.delete('tab')
  url.searchParams.delete('movie_id')
  window.location.href = url.pathname
}

onMounted(() => { fetchReviews(); fetchComments() })
</script>

<style scoped>
.admin-reviews { max-width: 1100px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.rating-cell { color: #e8a838; font-weight: 600; }
.paginator { margin-top: 16px; justify-content: flex-end; }
.filter-bar { margin-bottom: 12px; }
</style>
