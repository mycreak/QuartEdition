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
        <!-- 推荐理由 -->
        <div class="recommend-reason" v-if="showRecommendReason">
          {{ movie.recommend_reason || '为你探索更多可能' }}
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import type { Movie } from '@/types/movie'
import { formatRating, cleanUrl } from '@/utils/format'
import { VideoCamera, StarFilled } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  movie: Movie & { recommend_reason?: string }
  /** 是否显示推荐理由，默认不显示 */
  showRecommendReason?: boolean
}>(), {
  showRecommendReason: false
})
</script>

<style scoped>
.movie-card {
  width: 100%;
  cursor: pointer;
  transition: transform 0.2s;
}
.movie-card:hover {
  transform: translateY(-2px);
}
.card-poster {
  width: 100%;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 8px;
  position: relative;
}
.card-poster {
  aspect-ratio: 2/3;
}
.card-poster img,
.card-poster .poster-placeholder,
.card-poster .el-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
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
  background: #f5f7fa;
  color: #c0c4cc;
}
.card-body {
  padding: 0 2px;
}
.card-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin: 0 0 4px 0;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.card-rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #e6a23c;
}
.card-genres {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.genre-tag {
  --el-tag-font-size: 10px;
  --el-tag-padding: 0 3px;
  --el-tag-height: 16px;
  --el-tag-border-radius: 2px;
}
.recommend-reason {
  font-size: 11px;
  color: #909399;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
}
</style>
