<template>
  <div class="movie-card" @click="$router.push(`/movies/${movie.id}`)">
    <div class="card-poster">
      <el-image
        v-if="movie.poster_url"
        :src="cleanUrl(movie.poster_url)"
        fit="cover"
        referrerpolicy="no-referrer"
        class="poster-img"
      >
        <template #error>
          <div class="poster-placeholder">
            <el-icon :size="32"><VideoCamera /></el-icon>
          </div>
        </template>
      </el-image>
      <div v-else class="poster-placeholder">
        <el-icon :size="32"><VideoCamera /></el-icon>
      </div>
    </div>
    <div class="card-body">
      <h3 class="card-title" :title="movie.title">{{ movie.title }}</h3>
      <div class="card-meta">
        <span v-if="movie.release_year" class="card-year">{{ movie.release_year }}</span>
        <span v-if="movie.rating?.average" class="card-rating">
          <el-icon :size="14"><StarFilled /></el-icon>
          {{ formatRating(movie.rating.average) }}
        </span>
      </div>
      <div class="card-genres" v-if="movie.genres?.length">
        <el-tag
          v-for="genre in movie.genres.slice(0, 3)"
          :key="genre"
          size="small"
          class="genre-tag"
        >
          {{ genre }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Movie } from '@/types/movie'
import { formatRating } from '@/utils/format'
import { VideoCamera, StarFilled } from '@element-plus/icons-vue'

defineProps<{ movie: Movie }>()

/**
 * 清理URL中的多余字符（反引号、空格等）
 */
function cleanUrl(url: string): string {
  // 去掉前后的空格和反引号
  return url.replace(/^[\s`]+|[\s`]+$/g, '')
}
</script>

<style scoped>
.movie-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.movie-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

.card-poster {
  width: 100%;
  height: 280px;
  background: #f0f0f0;
  overflow: hidden;
}

.poster-img {
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
  background: linear-gradient(135deg, #e0e0e0, #f5f5f5);
}

.card-body {
  padding: 12px 14px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  margin: 0 0 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #888;
}

.card-year {
  color: #aaa;
}

.card-rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #e8a838;
  font-weight: 500;
}

.card-genres {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.genre-tag {
  font-size: 11px;
}
</style>
