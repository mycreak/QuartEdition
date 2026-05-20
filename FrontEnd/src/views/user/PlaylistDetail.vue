<template>
  <div class="playlist-detail-page" v-loading="loading">
    <ErrorAlert :message="error" @close="error = ''" />

    <template v-if="detail">
      <!-- 封面背景 -->
      <div
        class="detail-hero"
        :style="{ backgroundImage: detail.cover_url ? `url(${detail.cover_url})` : undefined }"
      >
        <div class="hero-overlay">
          <el-button class="hero-back" :icon="ArrowLeft" @click="router.push('/')" text>
            返回推荐
          </el-button>
          <h1 class="hero-title">{{ detail.title }}</h1>
          <p class="hero-desc" v-if="detail.description">{{ detail.description }}</p>
        </div>
      </div>

      <!-- 影片列表 -->
      <div class="movie-list">
        <div v-for="movie in detail.movies" :key="movie.id" class="movie-item">
          <!-- 序号 -->
          <div class="movie-index">{{ detail.movies.indexOf(movie) + 1 }}</div>

          <!-- 海报 -->
          <div class="movie-poster" @click="router.push(`/movies/${movie.id}?from=playlist&listId=${route.params.id}`)">
            <img
              v-if="movie.poster_url"
              :src="movie.poster_url"
              :alt="movie.title"
              referrerpolicy="no-referrer"
            />
            <div v-else class="poster-placeholder">
              <el-icon :size="36"><VideoCamera /></el-icon>
            </div>
          </div>

          <!-- 信息 + AI 总结 -->
          <div class="movie-body">
            <div class="movie-header">
              <h3 class="movie-title" @click="router.push(`/movies/${movie.id}?from=playlist&listId=${route.params.id}`)">
                {{ movie.title }}
              </h3>
              <div class="movie-meta">
                <span v-if="movie.release_year" class="meta-year">{{ movie.release_year }}</span>
                <span v-if="movie.rating" class="meta-rating">
                  <el-icon :size="14"><StarFilled /></el-icon>
                  {{ movie.rating.toFixed(1) }}
                </span>
              </div>
            </div>
            <!-- AI 总结 -->
            <p v-if="movie.ai_summary" class="movie-ai">{{ movie.ai_summary }}</p>
            <p v-else class="movie-ai empty">暂无 AI 总结</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { userApi } from '@/api/user'
import type { PlaylistDetail } from '@/types/movie'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import { VideoCamera, StarFilled, ArrowLeft } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const detail = ref<PlaylistDetail | null>(null)
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const res = await userApi.playlistDetail(id)
    detail.value = res.data
  } catch {
    error.value = '加载片单失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.playlist-detail-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 0 32px;
}

/* ── 封面区 ── */
.detail-hero {
  min-height: 340px;
  background-size: cover;
  background-position: center;
  background-color: #1a1a2e;
  display: flex;
  align-items: flex-end;
  margin-bottom: 0;
}

.hero-overlay {
  width: 100%;
  padding: 48px 32px 32px;
  background: linear-gradient(transparent 0%, rgba(0,0,0,0.5) 40%, rgba(0,0,0,0.85) 100%);
  color: #fff;
}

.hero-back {
  margin-bottom: 16px;
  color: rgba(255,255,255,0.7);
  padding-left: 0;
}
.hero-back:hover {
  color: #fff;
}

.hero-title {
  font-size: 32px;
  margin: 0 0 10px;
  font-weight: 700;
}

.hero-desc {
  font-size: 15px;
  margin: 0;
  opacity: 0.85;
  line-height: 1.7;
  max-width: 600px;
}

/* ── 影片列表 ── */
.movie-list {
  padding: 0 24px;
}

.movie-item {
  display: flex;
  gap: 20px;
  padding: 20px 0;
  border-bottom: 1px solid #f0f0f0;
}
.movie-item:last-child {
  border-bottom: none;
}

/* 序号 */
.movie-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 4px;
}

/* 海报 */
.movie-poster {
  width: 100px;
  height: 133px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  cursor: pointer;
  background: #f0f0f0;
  transition: transform 0.15s;
}
.movie-poster:hover {
  transform: scale(1.03);
}
.movie-poster img {
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
  color: #ccc;
}

/* 信息区 */
.movie-body {
  flex: 1;
  min-width: 0;
}

.movie-header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.movie-title {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
  cursor: pointer;
  color: #303133;
}
.movie-title:hover {
  color: #409eff;
}

.movie-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  color: #909399;
  white-space: nowrap;
}

.meta-rating {
  display: flex;
  align-items: center;
  gap: 3px;
  color: #e8a838;
  font-weight: 500;
}

/* AI 总结 */
.movie-ai {
  font-size: 13px;
  line-height: 1.65;
  color: #606266;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
.movie-ai.empty {
  color: #c0c4cc;
}
</style>
