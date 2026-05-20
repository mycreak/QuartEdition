<template>
  <div class="playlist-edit-page" v-loading="loading">
    <!-- 顶部栏 -->
    <div class="page-header">
      <div class="header-left">
        <el-button :icon="ArrowLeft" @click="handleBack">返回</el-button>
        <h2 class="page-title">{{ isEdit ? '编辑片单' : '新建片单' }}</h2>
      </div>
      <div class="header-right">
        <el-button @click="handleDiscard" :disabled="!hasUnsavedChanges">放弃修改</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving" :disabled="!canSave">保存</el-button>
      </div>
    </div>

    <!-- 主要内容区 -->
    <el-card class="main-card">
      <div class="content-grid">
        <!-- 左侧：封面 -->
        <div class="cover-section">
          <div class="section-label">封面</div>
          <div class="cover-hint">建议尺寸：1280×320（4:1）</div>
          <AvatarUpload
            v-model="store.cover_url"
            mode="cover"
            @success="onCoverSuccess"
          />
        </div>

        <!-- 右侧：基本信息 -->
        <div class="info-section">
          <el-form label-position="top" label-width="100px">
            <el-form-item label="片单名称 *">
              <el-input
                v-model="store.title"
                placeholder="请输入片单名称"
                maxlength="100"
                show-word-limit
              />
            </el-form-item>

            <el-form-item label="上架时间">
              <el-date-picker
                v-model="store.publish_at"
                type="datetime"
                placeholder="选择上架时间（可选）"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DDTHH:mm:ss"
                clearable
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item label="下架时间">
              <el-date-picker
                v-model="store.unpublish_at"
                type="datetime"
                placeholder="选择下架时间（可选）"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DDTHH:mm:ss"
                clearable
                style="width: 100%"
                :disabled-date="disabledUnpublishDate"
              />
            </el-form-item>

            <el-form-item label="排序权重">
              <el-input-number
                v-model="store.sort_order"
                :min="0"
                :max="9999"
                placeholder="数字越大越靠前"
                style="width: 100%"
              />
              <div class="form-hint">数字越大，片单在列表中越靠前；0 为默认值（普通优先级）</div>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <!-- 片单介绍 -->
      <el-divider />
      <div class="description-section">
        <div class="section-label">片单介绍</div>
        <el-input
          v-model="store.description"
          type="textarea"
          :rows="4"
          placeholder="请输入片单介绍（不超过160字）"
          maxlength="160"
          show-word-limit
        />
      </div>
    </el-card>

    <!-- 电影列表区 -->
    <el-card class="movies-card">
      <div class="movies-header">
        <div class="movies-title">
          <el-icon><VideoCamera /></el-icon>
          已添加电影（{{ store.movie_ids.length }} 部）
        </div>
        <el-button type="primary" :icon="Plus" @click="openMovieSelector">添加电影</el-button>
      </div>

      <div class="movie-list">
        <!-- 空状态 -->
        <div v-if="store.movies.length === 0" class="empty-movies">
          <el-empty description="还没有添加电影，点击右上角按钮添加">
            <template #image>
              <el-icon :size="60"><VideoCamera /></el-icon>
            </template>
          </el-empty>
        </div>

        <!-- 电影列表 -->
        <template v-else>
          <div
            v-for="(movie, index) in store.movies"
            :key="movie.id"
            class="movie-item"
            draggable="true"
            @dragstart="handleDragStart($event, index)"
            @dragover.prevent="handleDragOver"
            @drop="handleDrop($event, index)"
          >
            <!-- 序号 -->
            <div class="movie-index">
              <el-icon><Rank /></el-icon>
              {{ index + 1 }}
            </div>

            <!-- 海报 -->
            <div class="movie-poster" @click="goToMovieDetail(movie.id)">
              <el-image
                v-if="movie.poster_url"
                :src="movie.poster_url"
                fit="cover"
              />
              <div v-else class="poster-placeholder">
                <el-icon :size="24"><VideoCamera /></el-icon>
              </div>
            </div>

            <!-- 电影信息 -->
            <div class="movie-info" @click="goToMovieDetail(movie.id)">
              <div class="movie-title">{{ movie.title }}</div>
              <div class="movie-meta">
                <span v-if="movie.release_year" class="meta-item">{{ movie.release_year }}</span>
                <!-- 类型标签 -->
                <el-tag
                  v-for="g in getGenres(movie)"
                  :key="g.id || g"
                  size="small"
                  class="genre-tag"
                >{{ getGenreName(g) }}</el-tag>
                <!-- 地区标签 -->
                <el-tag
                  v-for="r in getRegions(movie)"
                  :key="r.id || r"
                  size="small"
                  class="region-tag"
                >{{ getRegionName(r) }}</el-tag>
                <!-- AI标签 -->
                <el-tag
                  v-for="(tag, idx) in movie.ai_tags"
                  :key="`ai-tag-${idx}`"
                  size="small"
                  class="ai-tag"
                >{{ tag }}</el-tag>
                <!-- 评分 -->
                <span v-if="movie.rating?.average" class="rating">
                  <el-icon :size="12"><Star /></el-icon>
                  {{ movie.rating.average.toFixed(1) }}
                </span>
              </div>
            </div>

            <!-- AI总结 -->
            <div class="movie-summary">
              <div class="summary-label">AI剧情总结</div>
              <p v-if="movie.ai_summary" class="summary-text">{{ movie.ai_summary }}</p>
              <p v-else class="summary-text empty">暂无AI剧情总结</p>
              <!-- 调试 -->
              <div v-if="false" style="font-size:10px;color:#999;">
                {{ JSON.stringify(movie) }}
              </div>
            </div>

            <!-- 操作 -->
            <div class="movie-actions">
              <el-button
                type="primary"
                link
                size="small"
                @click="goToMovieDetail(movie.id)"
              >详情</el-button>
              <el-button
                type="danger"
                link
                size="small"
                @click="handleRemoveMovie(movie.id)"
              >移除</el-button>
            </div>
          </div>
        </template>
      </div>
    </el-card>

    <!-- 电影选择器弹窗 -->
    <MovieSelector
      v-model="movieSelectorVisible"
      :excluded-movie-ids="store.movie_ids"
      :from-playlist-edit="true"
      @select="onMovieSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Plus, VideoCamera, Star, Rank } from '@element-plus/icons-vue'
import { usePlaylistEditStore } from '@/stores/playlistEdit'
import AvatarUpload from '@/components/common/AvatarUpload.vue'
import MovieSelector from '@/components/common/MovieSelector.vue'
import { adminPlaylistApi } from '@/api/admin/playlists'
import { adminMoviesApi } from '@/api/admin/movies'
import type { Movie } from '@/types/movie'

const router = useRouter()
const route = useRoute()
const store = usePlaylistEditStore()

const saving = ref(false)
const loading = ref(false)
const movieSelectorVisible = ref(false)
const draggedIndex = ref<number | null>(null)

const TYPE_MAP: Record<number, string> = {
  1: '纪录片', 2: '传记', 3: '犯罪', 4: '历史', 5: '动作',
  6: '情色', 7: '歌舞', 8: '儿童', 10: '悬疑', 11: '剧情',
  12: '灾难', 13: '爱情', 14: '音乐', 15: '冒险', 16: '奇幻',
  17: '科幻', 18: '运动', 19: '惊悚', 20: '恐怖', 22: '战争',
  23: '短片', 24: '喜剧', 25: '动画', 27: '西部', 28: '家庭',
  29: '武侠', 30: '古装', 31: '黑色电影',
}

// 获取类型数组（兼容对象和数字）
function getGenres(movie: any) {
  if (!movie.genres) return []
  return Array.isArray(movie.genres) ? movie.genres : []
}

// 获取类型名称
function getGenreName(g: any) {
  if (typeof g === 'object' && g.name) return g.name
  if (typeof g === 'number') return TYPE_MAP[g] || g
  return String(g)
}

// 获取地区数组（兼容对象和字符串）
function getRegions(movie: any) {
  if (!movie.regions) return []
  return Array.isArray(movie.regions) ? movie.regions : []
}

// 获取地区名称
function getRegionName(r: any) {
  if (typeof r === 'object' && r.name) return r.name
  return String(r)
}

const isEdit = computed(() => !!route.params.id)
const hasUnsavedChanges = computed(() => store.hasUnsavedChanges)
const canSave = computed(() => {
  return store.title.trim().length > 0 && store.movie_ids.length > 0
})

// 封面上传成功
const onCoverSuccess = () => {
  ElMessage.success('封面上传成功')
}

// 打开电影选择器
const openMovieSelector = () => {
  movieSelectorVisible.value = true
}

// 选择电影
const onMovieSelected = async (movie: Movie) => {
  try {
    const res = await adminMoviesApi.detail(movie.id)
    const fullMovie = {
      ...res.data.movie,
      genres: res.data.genres,
      regions: res.data.regions,
      ai_summary: res.data.ai_summary,
      ai_tags: res.data.ai_tags || [],
    }
    store.addMovie(fullMovie as any)
    ElMessage.success(`已添加「${movie.title}」`)
  } catch {
    store.addMovie(movie)
    ElMessage.success(`已添加「${movie.title}」`)
  }
}

// 移除电影
const handleRemoveMovie = (movieId: number) => {
  const movie = store.movies.find(m => m.id === movieId)
  ElMessageBox.confirm(
    `确定要从片单中移除「${movie?.title}」吗？`,
    '确认移除',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    store.removeMovie(movieId)
    ElMessage.success('已移除')
  }).catch(() => {
    // 取消
  })
}

// 拖拽相关
const handleDragStart = (e: DragEvent, index: number) => {
  draggedIndex.value = index
}

const handleDragOver = (e: DragEvent) => {
  e.dataTransfer!.dropEffect = 'move'
}

const handleDrop = (e: DragEvent, targetIndex: number) => {
  if (draggedIndex.value === null || draggedIndex.value === targetIndex) return

  const movies = [...store.movies]
  const movieIds = [...store.movie_ids]
  const [draggedMovie] = movies.splice(draggedIndex.value, 1)
  const [draggedId] = movieIds.splice(draggedIndex.value, 1)
  movies.splice(targetIndex, 0, draggedMovie)
  movieIds.splice(targetIndex, 0, draggedId)

  // 更新store
  store.movies.splice(0, store.movies.length, ...movies)
  store.movie_ids.splice(0, store.movie_ids.length, ...movieIds)

  draggedIndex.value = null
}

// 前往电影详情
const goToMovieDetail = (movieId: number) => {
  router.push({
    name: 'AdminMovieDetail',
    params: { id: movieId },
    query: { from: 'playlist-edit' }
  })
}

// 返回
const handleBack = async () => {
  if (store.hasUnsavedChanges) {
    try {
      await ElMessageBox.confirm(
        '你有未保存的修改，确定要返回吗？',
        '确认返回',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      // 用户确认返回
      store.clearState()
      router.back()
    } catch {
      // 用户取消
    }
  } else {
    store.clearState()
    router.back()
  }
}

// 放弃修改
const handleDiscard = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要放弃所有修改吗？',
      '确认放弃',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    if (isEdit.value) {
      // 重新加载
      loadPlaylist()
    } else {
      store.initState()
    }
    ElMessage.success('已重置')
  } catch {
    // 取消
  }
}

// 校验时间
function validateTime(): boolean {
  if (store.publish_at && store.unpublish_at) {
    const publishTime = new Date(store.publish_at)
    const unpublishTime = new Date(store.unpublish_at)
    if (publishTime >= unpublishTime) {
      ElMessage.warning('上架时间必须早于下架时间，请重新选择')
      return false
    }
  }
  
  if (store.unpublish_at) {
    const unpublishTime = new Date(store.unpublish_at)
    const now = new Date()
    if (unpublishTime <= now) {
      ElMessage.warning('下架时间不能早于当前时间，请重新选择')
      return false
    }
  }
  
  return true
}

// 禁用下架时间早于当前
function disabledUnpublishDate(time: Date) {
  return time.getTime() < Date.now() - 8.64e7
}

// 保存
const handleSave = async () => {
  if (!canSave.value) return
  
  if (!validateTime()) return

  saving.value = true
  try {
    if (isEdit.value) {
      await adminPlaylistApi.update(store.id!, {
        title: store.title,
        description: store.description,
        cover_url: store.cover_url,
        movie_ids: store.movie_ids,
        sort_order: store.sort_order,
        publish_at: store.publish_at,
        unpublish_at: store.unpublish_at,
      })
      ElMessage.success('保存成功')
    } else {
      await adminPlaylistApi.create({
        title: store.title,
        description: store.description,
        cover_url: store.cover_url,
        movie_ids: store.movie_ids,
        sort_order: store.sort_order,
        publish_at: store.publish_at,
        unpublish_at: store.unpublish_at,
      })
      ElMessage.success('创建成功')
    }

    store.clearState()
    router.push({ name: 'AdminMovies', query: { tab: 'playlists' } })
  } catch (err: any) {
    ElMessage.error(err.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// 加载片单
const loadPlaylist = async () => {
  if (!isEdit.value) return

  loading.value = true
  try {
    // 直接通过列表 API 查找片单（后端无分页，返回全部）
    const res = await adminPlaylistApi.list()
    const playlist = res.data.items.find(p => p.id === Number(route.params.id))
    if (!playlist) {
      ElMessage.error('片单不存在')
      router.back()
      return
    }

    // 设置基本信息
    store.title = playlist.title
    store.description = playlist.description || ''
    store.cover_url = playlist.cover_url || ''
    store.sort_order = playlist.sort_order || 0
    store.publish_at = playlist.publish_at
    store.unpublish_at = playlist.unpublish_at

    // 加载电影详情
    if (playlist.movie_ids?.length) {
      const movies = []
      for (const movieId of playlist.movie_ids) {
        try {
          const res = await adminMoviesApi.detail(movieId)
          movies.push({
            ...res.data.movie,
            genres: res.data.genres,
            regions: res.data.regions,
            ai_summary: res.data.ai_summary,
          })
        } catch {
          // 跳过加载失败的电影
        }
      }
      store.movies = movies as any[]
      store.movie_ids = movies.map(m => m.id)
    }
    
  } catch {
    ElMessage.error('加载片单失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const playlistId = Number(route.params.id)
  
  if (playlistId) {
    // 编辑模式：先尝试从 session 恢复（从电影详情返回时）
    const hasRestored = store.loadStateFromSession()
    if (hasRestored && store.id === playlistId) {
      // 返回的是当前编辑的片单，直接恢复即可
      return
    }
    // 首次加载或 session 不匹配，从 API 重新加载
    store.initState(playlistId)
    loadPlaylist()
  } else {
    // 新建模式：优先从 session 恢复（从电影详情返回时），否则初始化空状态
    const hasRestored = store.loadStateFromSession()
    if (!hasRestored) {
      store.initState()
    }
  }
})
</script>

<style scoped>
.playlist-edit-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  color: #1a1a2e;
}

.header-right {
  display: flex;
  gap: 12px;
}

.main-card,
.movies-card {
  margin-bottom: 24px;
}

.content-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 32px;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 12px;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.cover-section {
  width: 400px;
}

.cover-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.info-section {
  flex: 1;
}

.description-section {
  margin-top: 8px;
}

.movies-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.movies-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
}

.empty-movies {
  padding: 60px 0;
}

.movie-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.movie-item {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  cursor: grab;
  transition: all 0.2s;
}

.movie-item:hover {
  background: #eef2f7;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.movie-item:active {
  cursor: grabbing;
}

.movie-index {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 40px;
  font-weight: 600;
  color: #409eff;
  gap: 4px;
}

.movie-poster {
  width: 80px;
  height: 106px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  cursor: pointer;
  background: #e8e8e8;
}

.movie-poster img,
.movie-poster :deep(.el-image) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.poster-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}

.movie-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.movie-title {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 8px;
}

.movie-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  font-size: 13px;
  color: #909399;
}

.genre-tag {
  background: #ecf5ff;
  color: #409eff;
  border: none;
}

.region-tag {
  background: #f0f9ff;
  color: #0984e3;
  border: none;
}

.ai-tag {
  background: #e8f8f5;
  color: #1abc9c;
  border: none;
}

.meta-item {
  margin-right: 4px;
}

.rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #e6a23c;
  font-weight: 500;
}

.movie-summary {
  width: 300px;
  flex-shrink: 0;
}

.summary-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.summary-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.summary-text.empty {
  color: #c0c4cc;
  font-style: italic;
}

.movie-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
</style>
