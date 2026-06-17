<template>
  <div class="profile-page">
    <div class="page-header">
      <h2 class="page-title">个人中心</h2>
      <el-button :icon="HomeFilled" @click="router.push('/')">返回首页</el-button>
    </div>

    <!-- ── 个人信息编辑 ── -->
    <el-card class="profile-card" shadow="never">
      <el-form
        ref="formRef"
        :model="form"
        label-width="100px"
        :rules="rules"
        :disabled="loading"
      >
        <el-form-item label="头像">
          <AvatarUpload v-model="form.avatar_url" @success="handleAvatarUploadSuccess" />
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" disabled placeholder="用户名不可修改" />
        </el-form-item>
        <el-form-item label="昵称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="请输入昵称" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="我的权限" v-if="form.permissions.length">
          <div class="permissions-list">
            <el-tag v-for="perm in form.permissions" :key="perm" size="small" type="success" effect="light">
              {{ formatPermissionName(perm) }}
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSubmit" :loading="loading">保存修改</el-button>
          <el-button @click="openPasswordDialog">修改密码</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ── 用户画像 ── -->
    <el-card v-if="profileTagsRaw !== null" class="profile-card mt-4" shadow="never">
      <div class="profile-tags-header">
        <div class="profile-tags-header-left">
          <el-icon :size="18"><TrendCharts /></el-icon>
          <span class="profile-tags-title">你的历史观影偏好</span>
        </div>
        <div class="profile-tags-stats">
          <span class="stats-text">总标签 {{ profileTagsRaw.total_tags }} 个</span>
          <el-button
            :icon="profileTagsCollapsed ? ArrowDown : ArrowUp"
            link
            size="small"
            @click="profileTagsCollapsed = !profileTagsCollapsed"
          >
            {{ profileTagsCollapsed ? '展开' : '收起' }}
          </el-button>
        </div>
      </div>

      <div v-show="!profileTagsCollapsed">
        <template v-if="profileTagsRaw.tags.length">
          <div v-for="(group, dim) in dimensionData" :key="dim" class="dimension-section">
            <h4 class="dim-title">
              {{ formatDimensionName(dim as string) }}
              <span class="dim-meta">CV: {{ group.cv.toFixed(1) }}%</span>
            </h4>
            <div class="dim-tags">
              <el-tag
                v-for="tag in group.tags"
                :key="tag.label"
                size="default"
                class="profile-tag"
                :color="tagColor(tag.score)"
                effect="dark"
              >
                {{ tag.label }}
                <span class="tag-score">{{ tag.score.toFixed(1) }}</span>
              </el-tag>
            </div>
          </div>
        </template>
        <div v-else class="profile-tags-empty">
          <el-icon :size="32"><CollectionTag /></el-icon>
          <p>快去发现更多优质电影吧</p>
        </div>
      </div>
    </el-card>

    <!-- ── 我的电影列表 ── -->
    <el-card class="profile-card mt-4" shadow="never">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="想看" name="want_watch" />
        <el-tab-pane label="在看" name="watching" />
        <el-tab-pane label="看过" name="watched" />
        <el-tab-pane label="收藏" name="favorite" />
        <el-tab-pane label="我的评论" name="comments" />
      </el-tabs>

      <!-- 电影列表 -->
      <div v-if="activeTab !== 'comments'" v-loading="movieLoading" class="movie-list">
        <template v-if="movieItems.length">
          <div
            v-for="item in movieItems"
            :key="item.movie_id"
            class="movie-card-wrapper"
          >
            <router-link
              :to="`/movies/${item.movie_id}?from=profile`"
              class="movie-card-link"
            >
              <div v-if="item.poster_url" class="movie-card-poster">
                <img :src="item.poster_url" :alt="item.title" referrerpolicy="no-referrer" />
              </div>
              <div v-else class="movie-card-placeholder">
                <el-icon :size="24"><VideoCamera /></el-icon>
              </div>
              <div class="movie-card-info">
                <div class="title">{{ item.title }}</div>
                <div class="meta" v-if="item.release_year">{{ item.release_year }}</div>
              </div>
              <div class="movie-card-rating" v-if="item.rating">
                <el-icon :size="14"><StarFilled /></el-icon>
                {{ item.rating.toFixed(1) }}
              </div>
            </router-link>

            <!-- AI 总结区域 -->
            <div class="movie-card-summary">
              <div class="summary-header">
                <el-icon :size="16"><Document /></el-icon>
                <span>AI 剧情总结</span>
              </div>
              <p v-if="item.ai_summary" class="summary-text">{{ item.ai_summary }}</p>
              <p v-else class="summary-text empty">暂无长评总结</p>
            </div>
          </div>
        </template>
        <div v-else-if="!movieLoading" class="empty-state">
          <p>{{ tabEmptyText }}</p>
        </div>
      </div>

      <!-- 评论列表 -->
      <div v-else v-loading="commentLoading" class="movie-list">
        <template v-if="commentItems.length">
          <div v-for="item in commentItems" :key="item.movie_id" class="movie-card-wrapper">
            <router-link
              :to="`/movies/${item.movie_id}?from=profile`"
              class="movie-card-link"
            >
              <div v-if="item.poster_url" class="movie-card-poster">
                <img :src="item.poster_url" :alt="item.title" referrerpolicy="no-referrer" />
              </div>
              <div v-else class="movie-card-placeholder">
                <el-icon :size="24"><VideoCamera /></el-icon>
              </div>
              <div class="movie-card-info">
                <div class="title">{{ item.title || `电影 #${item.movie_id}` }}</div>
                <div class="meta" v-if="item.release_year">{{ item.release_year }}</div>
              </div>
              <div class="movie-card-rating" v-if="item.rating">
                <el-icon :size="14"><StarFilled /></el-icon>
                {{ item.rating }}
              </div>
            </router-link>
            <!-- 评论展示区域 -->
            <div class="movie-card-summary">
              <div class="summary-header">
                <div class="summary-header-left">
                  <el-icon :size="16"><Document /></el-icon>
                  <span>我的评论</span>
                </div>
                <el-button
                  type="danger"
                  link
                  size="small"
                  :icon="Delete"
                  :loading="deletingMovieId === item.movie_id"
                  @click="handleDeleteComment(item.movie_id)"
                >
                  删除
                </el-button>
              </div>
              <p class="summary-text">{{ item.text }}</p>
              <div v-if="item.date" class="comment-item-meta">
                <span>{{ item.date }}</span>
              </div>
            </div>
          </div>
        </template>
        <div v-else-if="!commentLoading" class="empty-state">
          <p>还没有发表评论</p>
        </div>
      </div>

      <Pagination
        v-if="activeTab !== 'comments' && movieTotal > moviePageSize"
        :current="moviePage"
        :total="movieTotal"
        :page-size="moviePageSize"
        @change="fetchMyMovies"
      />
      <Pagination
        v-if="activeTab === 'comments' && commentTotal > commentPageSize"
        :current="commentPage"
        :total="commentTotal"
        :page-size="commentPageSize"
        @change="fetchMyComments"
      />
    </el-card>

    <!-- ── 修改密码弹窗 ── -->
    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="440px" :close-on-click-modal="false">
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="80px"
        :disabled="passwordLoading"
      >
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="passwordForm.old_password" type="password" placeholder="请输入原密码" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passwordForm.new_password" type="password" placeholder="至少6位，含大/小写字母和数字" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="passwordForm.confirm_password" type="password" placeholder="请再次输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword" :loading="passwordLoading">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { updateProfile, changePassword } from '@/api/profile'
import { userActionApi } from '@/api/user'
import { getPermissionShortName } from '@/utils/permission'
import { HomeFilled, StarFilled, VideoCamera, Document, Delete, TrendCharts, CollectionTag, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import AvatarUpload from '@/components/common/AvatarUpload.vue'
import Pagination from '@/components/common/Pagination.vue'

const authStore = useAuthStore()
const router = useRouter()
const formRef = ref<FormInstance | null>(null)
const loading = ref(false)

const form = reactive({
  username: '',
  display_name: '',
  avatar_url: '',
  permissions: [] as import('@/utils/permission').PermissionCode[],
})

const rules: FormRules = {
  display_name: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 1, max: 64, message: '昵称长度在1到64个字符', trigger: 'blur' },
  ],
}

interface MovieItem {
  movie_id: number
  title: string
  poster_url?: string
  release_year?: number
  douban_id?: string
  rating?: number
  ai_summary?: string
}

interface CommentItem {
  movie_id: number
  title?: string
  poster_url?: string
  release_year?: number
  rating?: number
  text: string
  date?: string
}

const activeTab = ref('want_watch')
const movieItems = ref<MovieItem[]>([])
const movieLoading = ref(false)
const moviePage = ref(1)
const movieTotal = ref(0)
const moviePageSize = ref(5)

const commentItems = ref<CommentItem[]>([])
const commentLoading = ref(false)
const commentPage = ref(1)
const commentTotal = ref(0)
const commentPageSize = ref(10)
const deletingMovieId = ref<number | null>(null)

interface ProfileTag {
  dimension: string
  label: string
  score: number
  confidence?: number
  source: string
}

const profileTagsRaw = ref<{ tags: ProfileTag[]; total_tags: number } | null>(null)
const profileTagsLoading = ref(false)
const profileTagsCollapsed = ref(false)

interface DimensionGroup {
  tags: ProfileTag[]
  cv: number
}

/**
 * 按维度分组，每个维度取 Top10 标签，计算 CV 值
 *
 * CV（变异系数）= (标准差 / 均值) × 100
 *   值越高 → 维度内部评分差异越大（标签分散度高）
 *   值越低 → 维度内部评分越一致（标签集中度高）
 */
const dimensionData = computed<Record<string, DimensionGroup>>(() => {
  if (!profileTagsRaw.value) return {}

  const groups: Record<string, ProfileTag[]> = {}
  for (const t of profileTagsRaw.value.tags) {
    (groups[t.dimension] ||= []).push(t)
  }
  // 按 score 降序排列
  for (const dim of Object.keys(groups)) {
    groups[dim].sort((a, b) => b.score - a.score)
  }

  const result: Record<string, DimensionGroup> = {}
  for (const dim of Object.keys(groups)) {
    const all = groups[dim]
    const top10 = all.slice(0, 10)

    const scores = all.map(t => t.score)
    const mean = scores.reduce((s, x) => s + x, 0) / scores.length
    const variance = scores.reduce((s, x) => s + (x - mean) ** 2, 0) / scores.length
    const stdDev = Math.sqrt(variance)
    const cv = mean !== 0 ? (stdDev / mean) * 100 : 0

    result[dim] = { tags: top10, cv }
  }

  return result
})

const DIMENSION_LABELS: Record<string, string> = {
  director: '导演',
  actor: '演员',
  genre: '类型',
  era: '年代',
  region: '地区',
  overall: '综合',
  plot: '剧情',
  visual: '视觉',
  narrative: '叙事',
  pacing: '节奏',
}

function formatDimensionName(dim: string): string {
  return DIMENSION_LABELS[dim] || dim
}

function tagColor(score: number): string {
  if (score >= 8) return '#409eff'
  if (score >= 4) return '#67c23a'
  if (score >= 2) return '#e8a838'
  return '#909399'
}

const tabEmptyText = computed(() => {
  const map: Record<string, string> = {
    want_watch: '还没有标记想看的电影',
    watching: '还没有标记在看的电影',
    watched: '还没有标记看过的电影',
    favorite: '还没有收藏的电影',
  }
  return map[activeTab.value] || '暂无数据'
})

const formatPermissionName = getPermissionShortName

function initForm() {
  if (!authStore.user) return
  form.username = authStore.user.username
  form.display_name = authStore.user.display_name
  form.avatar_url = authStore.user.avatar_url || ''
  // 过滤掉 infra:* 权限，暂时不显示
  form.permissions = (authStore.user.permissions || []).filter(perm => !perm.startsWith('infra:')) as import('@/utils/permission').PermissionCode[]
}

function handleAvatarUploadSuccess(url: string) {
  form.avatar_url = url
  authStore.fetchUser()
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await updateProfile({
        display_name: form.display_name.trim(),
        avatar_url: form.avatar_url,
      })
      // 重新从服务端拉取用户数据，确保 Header 等组件即时刷新
      await authStore.fetchUser()
      ElMessage.success('保存成功')
      initForm()
    } catch (err: any) {
      ElMessage.error(err.response?.data?.message || '保存失败')
    } finally {
      loading.value = false
    }
  })
}

async function fetchMyMovies(page = 1): Promise<void> {
  if (activeTab.value === 'comments') return
  movieLoading.value = true
  moviePage.value = page
  try {
    const res = await userActionApi.myMovies(activeTab.value, page, moviePageSize.value)
    movieItems.value = res.data.items
    movieTotal.value = res.data.total
  } catch {
    movieItems.value = []
    movieTotal.value = 0
  } finally {
    movieLoading.value = false
  }
}

async function fetchMyTags(): Promise<void> {
  profileTagsLoading.value = true
  try {
    const res = await userActionApi.myTags()
    profileTagsRaw.value = {
      tags: res.data.tags || [],
      total_tags: res.data.total_tags || 0,
    }
  } catch {
    profileTagsRaw.value = { tags: [], total_tags: 0 }
  } finally {
    profileTagsLoading.value = false
  }
}

async function fetchMyComments(page = 1): Promise<void> {
  commentLoading.value = true
  commentPage.value = page
  try {
    const res = await userActionApi.myComments(page, commentPageSize.value)
    commentItems.value = res.data.items
    commentTotal.value = res.data.total
  } catch {
    commentItems.value = []
    commentTotal.value = 0
  } finally {
    commentLoading.value = false
  }
}

async function handleDeleteComment(movieId: number): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '确定要删除这条评论吗？',
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    deletingMovieId.value = movieId
    await userActionApi.deleteComment(movieId)
    ElMessage.success('删除成功')
    await fetchMyComments(commentPage.value)
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败，请稍后重试')
    }
  } finally {
    deletingMovieId.value = null
  }
}

function handleTabChange(tabName: string | number): void {
  const name = tabName as string
  activeTab.value = name
  if (name === 'comments') {
    commentPage.value = 1
    fetchMyComments(1)
  } else {
    moviePage.value = 1
    fetchMyMovies(1)
  }
}

const PASSWORD_UPPER = /[A-Z]/
const PASSWORD_LOWER = /[a-z]/
const PASSWORD_DIGIT = /\d/

const passwordDialogVisible = ref(false)
const passwordLoading = ref(false)
const passwordFormRef = ref<FormInstance | null>(null)
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const validatePasswordComplexity = (_rule: any, value: string, callback: any) => {
  if (!value) return callback(new Error('请输入新密码'))
  if (value.length < 6) return callback(new Error('密码至少 6 位'))
  if (!PASSWORD_UPPER.test(value)) return callback(new Error('必须包含至少一个大写字母'))
  if (!PASSWORD_LOWER.test(value)) return callback(new Error('必须包含至少一个小写字母'))
  if (!PASSWORD_DIGIT.test(value)) return callback(new Error('必须包含至少一个数字'))
  callback()
}

const validateConfirmPassword = (_rule: any, value: string, callback: any) => {
  if (!value) return callback(new Error('请再次输入新密码'))
  if (value !== passwordForm.new_password) return callback(new Error('两次密码不一致'))
  callback()
}

const passwordRules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [{ required: true, validator: validatePasswordComplexity, trigger: 'blur' }],
  confirm_password: [{ required: true, validator: validateConfirmPassword, trigger: 'blur' }],
}

function openPasswordDialog(): void {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  passwordFormRef.value?.resetFields()
  passwordDialogVisible.value = true
}

async function handleChangePassword(): Promise<void> {
  if (!passwordFormRef.value) return
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    passwordLoading.value = true
    try {
      await changePassword(passwordForm.old_password, passwordForm.new_password)
      ElMessage.success('密码修改成功，即将重新登录')
      passwordDialogVisible.value = false
      setTimeout(() => {
        authStore.logout()
        router.push('/login')
      }, 1000)
    } catch (err: any) {
      ElMessage.error(err.response?.data?.error || '修改失败，请稍后重试')
    } finally {
      passwordLoading.value = false
    }
  })
}

onMounted(() => {
  initForm()
  fetchMyMovies(1)
  fetchMyTags()
})
</script>

<style scoped>
.profile-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 30px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 24px;
  color: #1a1a2e;
  margin: 0;
}

.profile-card {
  border-radius: 8px;
  padding: 20px;
}

.profile-card.mt-4 {
  margin-top: 24px;
}

.permissions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.movie-list {
  min-height: 120px;
}

.movie-card-wrapper {
  padding: 12px 8px;
  border-bottom: 1px solid #f0f0f0;
}
.movie-card-wrapper:last-child {
  border-bottom: none;
}

.movie-card-link {
  display: flex;
  align-items: center;
  gap: 14px;
  text-decoration: none;
  color: inherit;
  border-radius: 6px;
  transition: background 0.15s;
}
.movie-card-link:hover {
  background: #f5f7fa;
}

.movie-card-poster {
  width: 60px;
  height: 80px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  background: #f0f0f0;
}
.movie-card-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.movie-card-placeholder {
  width: 60px;
  height: 80px;
  border-radius: 4px;
  background: #e8e8e8;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ccc;
}

.movie-card-info {
  flex: 1;
}
.movie-card-info .title {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}
.movie-card-info .meta {
  font-size: 12px;
  color: #909399;
}

.movie-card-rating {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 13px;
  color: #e8a838;
  font-weight: 500;
  white-space: nowrap;
}

.movie-card-summary {
  margin-top: 10px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
}

.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #606266;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.summary-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.summary-text {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.summary-text.empty {
  color: #c0c4cc;
  font-style: italic;
}

.movie-card-rating {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 13px;
  color: #e8a838;
  font-weight: 500;
  white-space: nowrap;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  color: #c0c4cc;
}

.comment-item {
  padding: 12px 8px;
  border-bottom: 1px solid #f0f0f0;
}
.comment-item:last-child {
  border-bottom: none;
}
.comment-item-title {
  font-size: 14px;
  font-weight: 500;
  color: #409eff;
  text-decoration: none;
  margin-bottom: 6px;
  display: inline-block;
}
.comment-item-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin-bottom: 4px;
}
.comment-item-meta {
  font-size: 12px;
  color: #909399;
  display: flex;
  gap: 10px;
  align-items: center;
}

/* ═══ 用户画像 ═══ */
.profile-tags-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.profile-tags-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-tags-title {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
}

.profile-tags-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 0;
  color: #c0c4cc;
  gap: 12px;
}

.profile-tags-empty p {
  font-size: 14px;
  margin: 0;
}

.profile-tags-stats {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stats-text {
  font-size: 13px;
  color: #909399;
}

.dimension-section {
  margin-bottom: 16px;
}

.dimension-section:last-child {
  margin-bottom: 0;
}

.dim-title {
  font-size: 14px;
  color: #606266;
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.dim-meta {
  font-size: 12px;
  color: #909399;
  font-weight: 400;
}

.dim-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile-tag {
  font-size: 13px;
}

.tag-score {
  margin-left: 4px;
  opacity: 0.85;
  font-size: 11px;
}
</style>
