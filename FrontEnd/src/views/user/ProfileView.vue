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
        </el-form-item>
      </el-form>
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
              :to="`/movies/${item.movie_id}`"
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
          <div v-for="item in commentItems" :key="item.movie_id" class="comment-item">
            <router-link :to="`/movies/${item.movie_id}`" class="comment-item-title">
              {{ item.title || `电影 #${item.movie_id}` }}
            </router-link>
            <div class="comment-item-text">{{ item.text }}</div>
            <div class="comment-item-meta">
              <span v-if="item.rating">
                <el-icon :size="12"><StarFilled /></el-icon> {{ item.rating }}
              </span>
              <span v-if="item.date">{{ item.date }}</span>
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
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { updateProfile } from '@/api/profile'
import { userActionApi } from '@/api/user'
import { getPermissionShortName } from '@/utils/permission'
import { HomeFilled, StarFilled, VideoCamera, Document } from '@element-plus/icons-vue'
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
  text: string
  rating?: number
  date?: string
}

const activeTab = ref('want_watch')
const movieItems = ref<MovieItem[]>([])
const movieLoading = ref(false)
const moviePage = ref(1)
const movieTotal = ref(0)
const moviePageSize = ref(15)

const commentItems = ref<CommentItem[]>([])
const commentLoading = ref(false)

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
      await authStore.updateProfile(res.data.data)
      ElMessage.success('保存成功')
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

async function fetchMyComments(): Promise<void> {
  commentLoading.value = true
  try {
    const res = await userActionApi.myComments(1, 50)
    commentItems.value = res.data.items
  } catch {
    commentItems.value = []
  } finally {
    commentLoading.value = false
  }
}

function handleTabChange(tabName: string | number): void {
  const name = tabName as string
  activeTab.value = name
  if (name === 'comments') {
    fetchMyComments()
  } else {
    moviePage.value = 1
    fetchMyMovies(1)
  }
}

onMounted(() => {
  initForm()
  fetchMyMovies(1)
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
  gap: 6px;
  color: #606266;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
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
</style>
