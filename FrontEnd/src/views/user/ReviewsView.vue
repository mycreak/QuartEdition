<template>
  <div v-loading="loading" class="reviews-page">
    <div class="reviews-header">
      <h1 class="reviews-title">最近评论</h1>
    </div>

    <ErrorAlert :message="error" @close="error = ''" />

    <div v-if="!loading && !reviews.length && !error" class="empty-state">
      <el-icon :size="48"><ChatLineRound /></el-icon>
      <p>暂无评论</p>
    </div>

    <div class="review-list">
      <div v-for="review in reviews" :key="review.id" class="review-item">
        <div class="review-header">
          <h3 class="review-title">
            <router-link :to="`/movies/${review.movie_id}`" class="movie-link">
              {{ review.title }}
            </router-link>
          </h3>
          <span v-if="review.rating" class="review-rating">
            <el-icon :size="14"><StarFilled /></el-icon>
            {{ formatRating(review.rating) }}
          </span>
        </div>
        <div class="review-meta">
          <span class="review-author">{{ review.author }}</span>
          <span class="review-date">{{ formatDateTime(review.created_at) }}</span>
        </div>
        <div class="review-content-wrapper">
          <div
            v-if="!review.expanded && review.content && review.content.length > 250"
            class="review-content-preview"
          >
            {{ review.content.slice(0, 250) }}...
          </div>
          <div
            v-else-if="review.expanded"
            class="review-content-full"
            v-html="formatContent(review.content)"
          ></div>
          <p
            v-else
            class="review-content"
          >{{ review.content }}</p>
          <el-button
            v-if="review.content && review.content.length > 250"
            type="primary"
            link
            size="small"
            @click="toggleReviewExpand(review)"
          >
            {{ review.expanded ? '收起' : '展开全文' }}
          </el-button>
        </div>
      </div>
    </div>

    <Pagination
      :current="page"
      :total="total"
      :page-size="pageSize"
      @change="handlePageChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { userApi } from '@/api/user'
import type { Review } from '@/types/review'
import Pagination from '@/components/common/Pagination.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import { formatRating, formatDateTime } from '@/utils/format'
import { ChatLineRound, StarFilled } from '@element-plus/icons-vue'

const reviews = ref<(Review & { expanded?: boolean })[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref('')

async function fetchReviews(p = 1): Promise<void> {
  loading.value = true
  error.value = ''
  page.value = p
  try {
    const res = await userApi.reviews({ movie_id: 0, page: p, page_size: pageSize.value })
    reviews.value = res.data.items
    total.value = res.data.total
  } catch (err: unknown) {
    error.value = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || '加载失败'
  } finally {
    loading.value = false
  }
}

function formatContent(content: string | undefined): string {
  if (!content) return ''
  return content.replace(/\n/g, '<br>')
}

function toggleReviewExpand(review: { expanded?: boolean }): void {
  review.expanded = !review.expanded
}

function handlePageChange(p: number): void {
  fetchReviews(p)
}

onMounted(() => {
  fetchReviews()
})
</script>

<style scoped>
.reviews-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 24px;
}

.reviews-header {
  margin-bottom: 24px;
}

.reviews-title {
  font-size: 22px;
  color: #1a1a2e;
  margin: 0;
}

.empty-state {
  text-align: center;
  color: #bbb;
  padding: 48px 0;
}

.empty-state p {
  margin-top: 12px;
  font-size: 15px;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-item {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.review-title {
  margin: 0;
  font-size: 16px;
}

.movie-link {
  color: #1a1a2e;
  text-decoration: none;
}

.movie-link:hover {
  color: #0f3460;
}

.review-rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #e8a838;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.review-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #aaa;
  margin-bottom: 12px;
}

.review-author {
  color: #0f3460;
}

.review-content-wrapper {
  margin-top: 4px;
}

.review-content-preview {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
}

.review-content-full {
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  color: #555;
  max-height: 300px;
  overflow-y: auto;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
}

.review-content {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
}
</style>
