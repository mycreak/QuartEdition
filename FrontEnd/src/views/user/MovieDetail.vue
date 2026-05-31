<template>
  <div v-loading="loading" class="detail-page">
    <!-- 从片单进入时显示返回按钮 -->
    <div v-if="fromPlaylist" class="back-bar">
      <el-button :icon="ArrowLeft" @click="goBackToPlaylist" text>
        返回片单
      </el-button>
    </div>
    <!-- 从管理端进入时显示返回按钮 -->
    <div v-else-if="fromAdmin" class="back-bar">
      <el-button :icon="ArrowLeft" @click="router.push('/')" text>
        返回推荐页
      </el-button>
    </div>
    <!-- 从个人中心进入时显示返回按钮 -->
    <div v-else-if="fromProfile" class="back-bar">
      <el-button :icon="ArrowLeft" @click="router.push('/profile')" text>
        返回个人中心
      </el-button>
    </div>
    <!-- 其他情况（直接从首页点击电影）：显示返回主页按钮 -->
    <div v-else class="back-bar">
      <el-button :icon="ArrowLeft" @click="router.push('/')" text>
        返回主页
      </el-button>
    </div>
    <ErrorAlert :message="error" @close="error = ''" />

    <template v-if="detail">
      <div class="detail-hero">
        <div class="detail-poster">
          <el-image
            v-if="detail.movie?.poster_url"
            :src="cleanUrl(detail.movie.poster_url)"
            fit="contain"
            referrerpolicy="no-referrer"
            class="poster-img"
          >
            <template #error>
              <div class="poster-placeholder">
                <el-icon :size="40"><VideoCamera /></el-icon>
              </div>
            </template>
          </el-image>
          <div v-else class="poster-placeholder">
            <el-icon :size="40"><VideoCamera /></el-icon>
          </div>
        </div>
        <div class="detail-info">
          <h1 class="detail-title">{{ detail.movie?.title }}</h1>

          <div class="detail-meta">
            <span v-if="detail.movie?.release_year" class="meta-item">{{ detail.movie.release_year }}</span>
            <span v-if="detail.rating?.average" class="meta-item rating-star">
              <el-icon :size="16"><StarFilled /></el-icon>
              {{ formatRating(detail.rating.average) }}
              <span class="rating-count">({{ formatCount(detail.rating.count) }}人评分)</span>
            </span>
          </div>

          <div v-if="detail.genres?.length" class="tag-row">
            <el-tag v-for="g in detail.genres" :key="g.id" size="small" class="genre-tag">{{ g.name }}</el-tag>
          </div>

          <div v-if="detail.regions?.length" class="tag-row">
            <el-tag v-for="r in detail.regions" :key="r.id" size="small" type="info">{{ r.name }}</el-tag>
          </div>
        </div>

        <div v-if="detail.rating?.distribution" class="detail-rating">
          <div class="rating-big">
            <span class="rating-score">{{ formatRating(detail.rating.average) }}</span>
            <span class="rating-total">{{ formatCount(detail.rating.count) }}人评分</span>
          </div>
          <div class="rating-bars">
            <div v-for="i in 5" :key="i" class="bar-row">
              <span class="bar-label">{{ i }}星</span>
              <el-progress
                :percentage="getStarPercent(6 - i)"
                :show-text="false"
                :stroke-width="8"
                color="#e8a838"
              />
            </div>
          </div>
        </div>
      </div>

      <el-divider />

      <div v-if="detail.directors?.length" class="section">
        <h2 class="section-title">导演</h2>
        <div class="person-list">
          <span v-for="d in detail.directors" :key="d.id" class="person-item">{{ d.name }}</span>
        </div>
      </div>

      <div v-if="detail.actors?.length" class="section">
        <h2 class="section-title">演员</h2>
        <div class="person-list">
          <span v-for="a in detail.actors" :key="a.id" class="person-item">{{ a.name }}</span>
        </div>
      </div>

      <div v-if="detail.crew && Object.keys(detail.crew).length" class="section">
        <h2 class="section-title">演职人员</h2>
        <div v-for="(members, role) in detail.crew" :key="role" class="crew-group">
          <span class="crew-role">{{ formatCrewRole(role) }}:</span>
          <span class="crew-names">{{ members.map((m: { name: string }) => m.name).join(' / ') }}</span>
        </div>
      </div>

      <!-- AI 总结 -->
      <div class="section">
        <h2 class="section-title">
          <el-icon style="color: #409eff; margin-right: 4px;"><MagicStick /></el-icon>
          AI 剧情总结
        </h2>
        <p v-if="detail.ai_summary" class="ai-summary">{{ detail.ai_summary }}</p>
        <p v-else class="ai-summary empty">暂无AI总结</p>
      </div>

      <!-- AI 标签 -->
      <div class="section">
        <h2 class="section-title">
          <el-icon style="color: #67c23a; margin-right: 4px;"><CollectionTag /></el-icon>
          AI 标签
        </h2>
        <div v-if="detail.ai_tags?.length" class="tag-row">
          <el-tag 
            v-for="tag in detail.ai_tags" 
            :key="tag" 
            size="small" 
            type="success"
            effect="light"
          >
            {{ tag }}
          </el-tag>
        </div>
        <p v-else class="empty">暂无AI标签</p>
      </div>

      <!-- 短评词云 -->
      <div class="section">
        <h2 class="section-title">
          <el-icon style="color: #8b5cf6; margin-right: 4px;"><ChatDotRound /></el-icon>
          短评词云
        </h2>
        <CommentWordCloud 
          :words="wordCloudWords" 
          :loading="wordCloudLoading" 
          :error="wordCloudError"
          @word-click="handleWordClick"
          @retry="fetchWordCloud(Number(route.params.id))"
        />
      </div>

      <!-- ── 用户操作按钮组 ── -->
      <div class="section">
        <h2 class="section-title">我的标记</h2>
        <div class="action-button-group">
          <el-button
            :type="actionState.want_watch ? 'primary' : 'default'"
            :icon="Star"
            :loading="actionLoading === 'want_watch'"
            @click="toggleAction('want_watch')"
          >
            {{ actionState.want_watch ? '已想看' : '想看' }}
          </el-button>
          <el-button
            :type="actionState.watching ? 'primary' : 'default'"
            :icon="VideoPlay"
            :loading="actionLoading === 'watching'"
            @click="toggleAction('watching')"
          >
            {{ actionState.watching ? '在看中' : '在看' }}
          </el-button>
          <el-button
            :type="actionState.watched ? 'success' : 'default'"
            :icon="Check"
            :loading="actionLoading === 'watched'"
            @click="toggleAction('watched')"
          >
            {{ actionState.watched ? '已看过' : '看过' }}
          </el-button>
          <el-button
            :type="actionState.favorite ? 'warning' : 'default'"
            :icon="CollectionTag"
            :loading="actionLoading === 'favorite'"
            @click="toggleAction('favorite')"
          >
            {{ actionState.favorite ? '已收藏' : '收藏' }}
          </el-button>
        </div>

        <!-- 评论入口 -->
        <div class="review-entry" v-if="actionState.watched">
          <!-- 已评论：显示占位 + 删除按钮 -->
          <div v-if="actionState.reviewed" class="reviewed-placeholder">
            <el-alert
              title="你已发表评论，每部电影只能评论一次"
              type="warning"
              :closable="false"
              show-icon
            />
            <el-button
              class="mt-3"
              type="danger"
              plain
              :loading="actionLoading === 'review'"
              @click="deleteReview"
            >
              删除已有评论
            </el-button>
          </div>
          <!-- 已提交（刚发布的 optimistic UI） -->
          <el-alert
            v-else-if="reviewSubmitted"
            title="评论已发布"
            type="success"
            :closable="false"
            show-icon
          />
          <!-- 未评论：显示表单 -->
          <div v-else class="review-form">
            <el-rate
              v-model="reviewRating"
              :max="5"
              :texts="['很差', '较差', '还行', '推荐', '力荐']"
              show-text
              class="mb-3"
            />
            <p v-if="reviewRating > 0" class="rating-hint">
              <template v-if="reviewRating >= 4">👍 好评将增加同类电影推荐</template>
              <template v-else-if="reviewRating <= 2">👎 差评将减少同类电影推荐</template>
              <template v-else>🤝 中性评价不影响推荐</template>
            </p>
            <el-input
              v-model="reviewText"
              type="textarea"
              :rows="3"
              placeholder="写下你对这部电影的看法吧（最多120字）..."
              maxlength="120"
              show-word-limit
            />
            <div class="mt-3" style="text-align: right;">
              <el-button
                type="primary"
                :disabled="!reviewText.trim()"
                :loading="actionLoading === 'review'"
                @click="submitReview"
              >
                发布评论
              </el-button>
            </div>
          </div>
        </div>
        <el-alert
          v-else
          title="标记看过之后才能评论哦"
          type="info"
          :closable="false"
          show-icon
        />
        <div v-if="actionError" class="mt-3">
          <el-alert :title="actionError" type="error" @close="actionError = ''" show-icon />
        </div>
      </div>
    </template>

    <el-divider />

    <el-tabs v-model="activeTab" class="review-tabs">
      <el-tab-pane label="短评" name="comments">
        <!-- 筛选提示 -->
        <div v-if="filterKeyword" class="filter-alert mb-4">
          <div class="flex justify-between items-center bg-blue-50 p-3 rounded text-blue-700 text-sm">
            <span>当前正在筛选包含关键词 <strong>{{ filterKeyword }}</strong> 的短评</span>
            <el-button type="text" size="small" @click="clearFilter">清空筛选</el-button>
          </div>
        </div>
        <div v-for="comment in filteredCommentList" :key="comment.id" class="comment-card">
          <div class="comment-card-header">
            <span class="comment-card-author">{{ comment.author }}</span>
            <span v-if="comment.rating" class="comment-card-rating">
              <el-icon :size="14"><StarFilled /></el-icon>
              {{ formatRating(comment.rating) }}
            </span>
          </div>
          <div class="comment-card-content-wrapper">
            <div
              v-if="!comment.expanded && getCommentContent(comment).length > 150"
              class="comment-card-content-preview"
              v-html="highlightKeyword(getCommentContent(comment).slice(0, 150) + '...', filterKeyword)"
            ></div>
            <div
              v-else-if="comment.expanded"
              class="comment-card-content-full"
              v-html="highlightKeyword(formatContent(getCommentContent(comment)), filterKeyword)"
            ></div>
            <p
              v-else
              class="comment-card-content"
              v-html="highlightKeyword(getCommentContent(comment), filterKeyword)"
            ></p>
            <el-button
              v-if="getCommentContent(comment).length > 150"
              type="primary"
              link
              size="small"
              @click="toggleCommentExpand(comment)"
            >
              {{ comment.expanded ? '收起' : '展开全文' }}
            </el-button>
          </div>
        </div>
        <div v-if="!filteredCommentList.length && !commentLoading" class="empty-tab">
          {{ filterKeyword ? '没有找到包含该关键词的短评' : '暂无内容' }}
        </div>
        <Pagination
          v-if="commentTotal > commentPageSize"
          :current="commentPage"
          :total="commentTotal"
          :page-size="commentPageSize"
          @change="handleCommentPageChange"
        />
      </el-tab-pane>

      <el-tab-pane label="长评" name="reviews">
        <div v-for="review in reviewList" :key="review.id || review._id" class="review-card">
          <div class="review-card-header">
            <span class="review-card-author">{{ review.author || '匿名用户' }}</span>
            <span v-if="review.rating" class="review-card-rating">
              <el-icon :size="14"><StarFilled /></el-icon>
              {{ formatRating(review.rating) }}
            </span>
          </div>
          <div class="review-card-content-wrapper">
            <div
              v-if="!review.expanded && getReviewContent(review).length > 200"
              class="review-card-content-preview"
            >
              {{ getReviewContent(review).slice(0, 200) }}...
            </div>
            <div
              v-else-if="review.expanded"
              class="review-card-content-full"
              v-html="formatContent(getReviewContent(review))"
            ></div>
            <p
              v-else
              class="review-card-content"
            >{{ getReviewContent(review) }}</p>
            <el-button
              v-if="getReviewContent(review).length > 200"
              type="primary"
              link
              size="small"
              @click="toggleReviewExpand(review)"
            >
              {{ review.expanded ? '收起' : '展开全文' }}
            </el-button>
          </div>
        </div>
        <div v-if="!reviewList.length && !reviewLoading" class="empty-tab">
          暂无内容
        </div>
        <Pagination
          v-if="reviewTotal > reviewPageSize"
          :current="reviewPage"
          :total="reviewTotal"
          :page-size="reviewPageSize"
          @change="handleReviewPageChange"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useMovieStore } from '@/stores/movies'
import type { MovieDetail, WordCloudItem, MovieStatus } from '@/types/movie'
import type { Review, Comment } from '@/types/review'
import { userApi, userActionApi } from '@/api/user'
import { moviesApi } from '@/api/movies'
import Pagination from '@/components/common/Pagination.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import CommentWordCloud from '@/components/common/CommentWordCloud.vue'
import { formatRating, formatCount, formatCrewRole } from '@/utils/format'
import { StarFilled, VideoCamera, MagicStick, CollectionTag, ChatDotRound, Star, VideoPlay, Check, ArrowLeft } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const store = useMovieStore()

// 判断是否从片单页进入
const fromPlaylist = computed(() => route.query.from === 'playlist')
const playlistId = computed(() => route.query.listId as string)

// 判断是否从管理端进入
const fromAdmin = computed(() => route.query.from === 'admin')

// 判断是否从个人中心进入
const fromProfile = computed(() => route.query.from === 'profile')

// 返回片单详情页
function goBackToPlaylist() {
  if (playlistId.value) {
    router.push(`/playlist/${playlistId.value}`)
  } else {
    router.back()
  }
}

const detail = ref<MovieDetail | null>(null)

/**
 * 清理URL中的多余字符（反引号、空格等）
 */
function cleanUrl(url: string): string {
  // 去掉前后的空格和反引号
  return url.replace(/^[\s`]+|[\s`]+$/g, '')
}
const loading = ref(false)
const error = ref('')

const reviewList = ref<(Review & { expanded?: boolean })[]>([])
const reviewPage = ref(1)
const reviewTotal = ref(0)
const reviewPageSize = ref(15)
const reviewLoading = ref(false)

const commentList = ref<(Comment & { expanded?: boolean })[]>([])
const commentPage = ref(1)
const commentTotal = ref(0)
const commentPageSize = ref(15)
const commentLoading = ref(false)

const activeTab = ref('comments')

// ── 用户行为状态 ──
const actionState = reactive<MovieStatus>({
  movie_id: 0,
  want_watch: false,
  watching: false,
  watched: false,
  favorite: false,
  reviewed: false,
})
const actionLoading = ref<string | null>(null)
const actionError = ref('')
const reviewText = ref('')
const reviewRating = ref(0)
const reviewSubmitted = ref(false)

// 词云相关
const wordCloudWords = ref<WordCloudItem[]>([])
const wordCloudLoading = ref(false)
const wordCloudError = ref('')
const filterKeyword = ref('')
const filteredCommentList = computed(() => {
  if (!filterKeyword.value) return commentList.value
  const keyword = filterKeyword.value.toLowerCase()
  return commentList.value.filter(c => c.content?.toLowerCase().includes(keyword))
})

function getStarPercent(stars: number): number {
  if (!detail.value?.rating?.distribution) return 0
  const { count, distribution } = detail.value.rating
  if (!count) return 0
  const key = String(stars)
  const val = Number(distribution[key]) || 0
  return Math.round((val / count) * 100)
}

function getCommentContent(comment: any): string {
  return comment.content || comment.text || ''
}

function getReviewContent(review: any): string {
  return review.content || review.text || ''
}

async function fetchWordCloud(movieId: number): Promise<void> {
  wordCloudLoading.value = true
  wordCloudError.value = ''
  try {
    const res = await moviesApi.getWordCloud(movieId)
    if (res.data.success) {
      wordCloudWords.value = res.data.data.words
    } else {
      wordCloudError.value = '词云生成失败'
    }
  } catch (err: any) {
    wordCloudError.value = err.response?.data?.error || '加载失败，请稍后重试'
    wordCloudWords.value = []
  } finally {
    wordCloudLoading.value = false
  }
}

async function loadDetail(id: number): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const data = await store.fetchDetail(id)
    if (data) {
      detail.value = data
      // 加载词云
      fetchWordCloud(id)
    } else {
      error.value = '电影不存在'
    }
  } catch {
    error.value = '加载失败'
  } finally {
    loading.value = false
  }
}

function handleWordClick(word: WordCloudItem): void {
  filterKeyword.value = word.text
  activeTab.value = 'comments'
  // 滚动到短评区域
  nextTick(() => {
    document.querySelector('.review-tabs')?.scrollIntoView({ behavior: 'smooth' })
  })
}

function clearFilter(): void {
  filterKeyword.value = ''
}

function formatContent(content: string | undefined): string {
  if (!content) return ''
  // 将换行符转换为 <br> 标签，保留段落格式
  return content.replace(/\n/g, '<br>')
}

function highlightKeyword(content: string | undefined, keyword: string): string {
  if (!content || !keyword) return content || ''
  // 转义正则特殊字符
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const reg = new RegExp(`(${escapedKeyword})`, 'gi')
  return content.replace(reg, '<span class="bg-yellow-200 font-bold">$1</span>')
}

function toggleReviewExpand(review: { expanded?: boolean }): void {
  review.expanded = !review.expanded
}

function toggleCommentExpand(comment: { expanded?: boolean }): void {
  comment.expanded = !comment.expanded
}

async function fetchReviews(p = 1): Promise<void> {
  const movieId = Number(route.params.id)
  if (!movieId) return
  reviewLoading.value = true
  reviewPage.value = p
  try {
    const res = await userApi.reviews({ movie_id: movieId, page: p, page_size: reviewPageSize.value })
    reviewList.value = res.data.items
    reviewTotal.value = res.data.total
  } catch {
    reviewList.value = []
  } finally {
    reviewLoading.value = false
  }
}

async function fetchComments(p = 1): Promise<void> {
  const movieId = Number(route.params.id)
  if (!movieId) return
  commentLoading.value = true
  commentPage.value = p
  try {
    const res = await userApi.comments({ movie_id: movieId, page: p, page_size: commentPageSize.value })
    commentList.value = res.data.items
    commentTotal.value = res.data.total
  } catch {
    commentList.value = []
  } finally {
    commentLoading.value = false
  }
}

function handleReviewPageChange(p: number): void {
  fetchReviews(p)
}

function handleCommentPageChange(p: number): void {
  fetchComments(p)
}

// ── 用户行为操作 ──

/** 加载用户对该电影的标记状态 */
async function loadActionStatus(movieId: number): Promise<void> {
  try {
    console.log('[MovieDetail] loading action status for movie:', movieId)
    const res = await userActionApi.status(movieId)
    console.log('[MovieDetail] status response:', res.data)
    Object.assign(actionState, res.data)
  } catch {
    console.warn('[MovieDetail] loadActionStatus failed (likely not logged in)')
  }
}

/** 切换标记状态（标记 / 取消） */
async function toggleAction(action: string): Promise<void> {
  const movieId = Number(route.params.id)
  if (!movieId) return
  actionLoading.value = action
  actionError.value = ''
  console.log('[MovieDetail] toggleAction:', action, 'movieId:', movieId, 'current:', (actionState as any)[action])
  try {
    if ((actionState as any)[action]) {
      // 取消
      await userActionApi.unmark(movieId, action)
      ;(actionState as any)[action] = false
    } else {
      // 标记
      await userActionApi.mark(movieId, action)
      // 观看状态机递进：设为当前 action，清零其他观看标记
      if (['want_watch', 'watching', 'watched'].includes(action)) {
        actionState.want_watch = false
        actionState.watching = false
        actionState.watched = false
        ;(actionState as any)[action] = true
        // 标记"看过"后显示评论入口
        if (action === 'watched') {
          reviewSubmitted.value = false
        }
      } else {
        ;(actionState as any)[action] = !(actionState as any)[action]
      }
    }
    // 刷新状态（确保服务器端状态一致）
    await loadActionStatus(movieId)
  } catch (err: any) {
    actionError.value = err.response?.data?.error || '操作失败，请稍后重试'
  } finally {
    actionLoading.value = null
  }
}

/** 提交评论 */
async function submitReview(): Promise<void> {
  const movieId = Number(route.params.id)
  if (!movieId || !reviewText.value.trim()) return
  try {
    await ElMessageBox.confirm(
      '确定要提交这条评论吗？提交后将无法修改，只能删除。',
      '确认提交',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    actionLoading.value = 'review'
    actionError.value = ''
    await userActionApi.comment(movieId, {
      review_text: reviewText.value.trim(),
      rating: reviewRating.value || undefined,
    })
    reviewSubmitted.value = true
    reviewText.value = ''
    reviewRating.value = 0
    actionState.reviewed = true
    // 刷新短评列表，让用户看到刚发的评论
    fetchComments(1)
  } catch (err: any) {
    if (err !== 'cancel') {
      actionError.value = err.response?.data?.error || '评论失败，请稍后重试'
    }
  } finally {
    actionLoading.value = null
  }
}

/** 删除评论 */
async function deleteReview(): Promise<void> {
  const movieId = Number(route.params.id)
  if (!movieId) return
  actionLoading.value = 'review'
  actionError.value = ''
  try {
    await userActionApi.deleteComment(movieId)
    actionState.reviewed = false
    reviewSubmitted.value = false
    reviewText.value = ''
    reviewRating.value = 0
    // 刷新评论列表
    fetchComments(1)
  } catch (err: any) {
    actionError.value = err.response?.data?.error || '删除失败，请稍后重试'
  } finally {
    actionLoading.value = null
  }
}

watch(() => route.params.id, async (newId) => {
  if (newId) {
    const id = Number(newId)
    await loadDetail(id)
    loadActionStatus(id)
    fetchReviews()
    fetchComments()
  }
}, { immediate: true })

onMounted(async () => {
  const id = Number(route.params.id)
  if (!id) return
  await loadDetail(id)
  loadActionStatus(id)
  fetchReviews()
  fetchComments()
})
</script>

<style scoped>
.detail-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 16px 24px 32px;
}

.back-bar {
  margin-bottom: 8px;
  position: relative;
  top: -8px;
}

.detail-hero {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}

.detail-poster {
  width: 200px;
  flex-shrink: 0;
}

.poster-img {
  width: 200px;
  min-height: 280px;
  border-radius: 6px;
  background: #f0f0f0;
}

.poster-placeholder {
  width: 200px;
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ccc;
  background: linear-gradient(135deg, #e0e0e0, #f5f5f5);
  border-radius: 6px;
}

.detail-info {
  flex: 1;
  min-width: 300px;
}

.detail-title {
  font-size: 26px;
  color: #1a1a2e;
  margin: 0 0 12px;
}

.detail-meta {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
}

.meta-item {
  color: #888;
}

.rating-star {
  display: flex;
  align-items: center;
  gap: 3px;
  color: #e8a838;
  font-weight: 500;
}

.rating-count {
  color: #aaa;
  font-weight: 400;
  font-size: 13px;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.genre-tag {
  background: #e8a838;
  border-color: #e8a838;
  color: #fff;
}

.detail-rating {
  min-width: 240px;
  background: #f9f9f9;
  border-radius: 8px;
  padding: 20px 24px;
}

.rating-big {
  text-align: center;
  margin-bottom: 16px;
}

.rating-score {
  font-size: 36px;
  font-weight: 700;
  color: #e8a838;
  display: block;
}

.rating-total {
  font-size: 13px;
  color: #aaa;
}

.rating-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-label {
  font-size: 12px;
  color: #888;
  width: 24px;
  text-align: right;
}

.bar-row :deep(.el-progress) {
  flex: 1;
}

.section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 17px;
  color: #1a1a2e;
  margin: 0 0 12px;
}

.person-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.person-item {
  font-size: 14px;
  color: #555;
}

.person-item::after {
  content: '/';
  color: #ddd;
  margin-left: 12px;
}

.person-item:last-child::after {
  content: '';
}

.crew-group {
  font-size: 14px;
  margin-bottom: 6px;
}

.crew-role {
  color: #888;
  margin-right: 8px;
}

.crew-names {
  color: #555;
}

.review-tabs {
  margin-top: 8px;
}

.review-card,
.comment-card {
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
}

.review-card:last-child,
.comment-card:last-child {
  border-bottom: none;
}

.review-card-header,
.comment-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.review-card-author,
.comment-card-author {
  font-size: 14px;
  font-weight: 600;
  color: #0f3460;
}

.review-card-rating,
.comment-card-rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #e8a838;
  font-size: 14px;
  font-weight: 500;
}

.review-card-content-wrapper,
.comment-card-content-wrapper {
  margin-top: 4px;
}

.review-card-content-preview,
.comment-card-content-preview {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
}

.review-card-content-full,
.comment-card-content-full {
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

.review-card-content,
.comment-card-content {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
}

.empty-tab {
  text-align: center;
  color: #ccc;
  padding: 32px 0;
  font-size: 14px;
}

.ai-summary {
  line-height: 1.8;
  color: #606266;
  padding: 8px 0 12px 0;
  text-indent: 2em;
}
.ai-summary.empty,
.empty {
  color: #c0c4cc;
  text-align: center;
  text-indent: 0;
  padding: 32px 0;
  margin: 0;
}

/* 关键词高亮 */
:deep(.bg-yellow-200) {
  background: #fef08a !important;
  padding: 1px 2px;
  border-radius: 2px;
}

/* 用户行为按钮组 */
.action-button-group {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.review-entry {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.reviewed-placeholder .mt-3 {
  margin-top: 12px;
}

.review-form .mb-3 {
  margin-bottom: 12px;
}

.rating-hint {
  font-size: 13px;
  color: #909399;
  margin: 0 0 8px 0;
  text-align: center;
}

.review-form .mt-3 {
  margin-top: 12px;
}
</style>
