<template>
  <div class="home-page">
    <!-- ═══════════════════════════════════════════════════════════
         左侧固定：猜你喜欢
         ═══════════════════════════════════════════════════════════ -->
    <aside class="recommend-sidebar">
      <div class="recommend-header">
        <h2 class="section-title">猜你喜欢</h2>
        <el-button :icon="Refresh" :loading="recommendLoading" @click="fetchRecommend" text size="small">
          刷新
        </el-button>
      </div>

      <div v-loading="recommendLoading" class="recommend-list">
        <ErrorAlert :message="recommendError" @close="recommendError = ''" />
        <template v-if="!recommendLoading && !recommendItems.length && !recommendError">
          <div class="empty-state">
            <el-icon :size="32"><Search /></el-icon>
            <p>暂无推荐</p>
          </div>
        </template>
        <div
          v-for="item in recommendItems"
          :key="item.movie_id"
          class="recommend-item"
          @click="router.push(`/movies/${item.movie_id}`)"
        >
          <div class="recommend-poster">
            <img v-if="item.poster_url" :src="item.poster_url" :alt="item.title" referrerpolicy="no-referrer" />
            <el-icon v-else :size="28"><VideoCamera /></el-icon>
          </div>
          <div class="recommend-info">
            <div class="recommend-title">{{ item.title }}</div>
            <div class="recommend-meta">
              <span v-if="item.release_year">{{ item.release_year }}</span>
              <span v-if="item.rating" class="recommend-rating">
                <el-icon :size="12"><StarFilled /></el-icon>
                {{ item.rating.toFixed(1) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- ═══════════════════════════════════════════════════════════
         右侧主内容区
         ═══════════════════════════════════════════════════════════ -->
    <div class="main-content">
      <!-- 1. 片单轮播 -->
      <div v-if="playlists.length" class="playlist-carousel">
        <el-carousel :interval="5000" trigger="click" height="320px" arrow="always" indicator-position="none">
          <el-carousel-item v-for="pl in playlists" :key="pl.id">
            <div
              class="carousel-item"
              :style="{ backgroundImage: pl.cover_url ? `url(${pl.cover_url})` : undefined }"
              @click="router.push(`/playlist/${pl.id}`)"
            >
              <div class="carousel-overlay">
                <h3 class="carousel-title">{{ pl.title }}</h3>
                <p class="carousel-desc" v-if="pl.description">{{ pl.description }}</p>
              </div>
            </div>
          </el-carousel-item>
        </el-carousel>
      </div>
      <div v-else class="playlist-carousel-placeholder">
        <el-empty description="现在还没有片单，敬请期待！" :image-size="100" />
      </div>

      <!-- 2. 搜索栏 -->
      <div class="home-filters">
        <el-input
          v-model="keyword"
          placeholder="搜索电影名称..."
          :prefix-icon="Search"
          clearable
          class="search-input"
          @clear="handleFilterChange"
          @keyup.enter="handleFilterChange"
        />
        <el-select
          v-model="selectedType"
          placeholder="全部类型"
          clearable
          class="filter-select"
          @change="handleFilterChange"
        >
          <el-option
            v-for="t in filterPacket?.types"
            :key="t.type_num"
            :label="t.type_name"
            :value="t.type_num"
          />
        </el-select>
        <el-select
          v-model="selectedRegion"
          placeholder="全部地区"
          clearable
          class="filter-select"
          @change="handleFilterChange"
        >
          <el-option
            v-for="r in filterPacket?.regions"
            :key="r"
            :label="r"
            :value="r"
          />
        </el-select>
        <el-input
           v-model="selectedYearInput"
           placeholder="年份"
           clearable
           class="filter-select"
           @change="handleYearChange"
           @clear="selectedYear = undefined; handleFilterChange()"
         />
        <el-select
          v-model="selectedRating"
          placeholder="评分"
          clearable
          class="filter-select"
          @change="handleFilterChange"
        >
          <el-option
            v-for="iv in filterPacket?.intervals"
            :key="iv.interval_id"
            :label="iv.label"
            :value="iv.interval_id"
          />
        </el-select>
      </div>

      <!-- 3. 影片列表 -->
      <section class="movie-section">
        <ErrorAlert :message="store.error" @close="store.error = ''" />

        <div v-loading="store.loading" class="movie-grid" :class="{ 'is-empty': !store.loading && !store.movies.length }">
          <template v-if="!store.loading && !store.movies.length && !store.error">
            <div class="empty-state">
              <el-icon :size="48"><Search /></el-icon>
              <p>没有找到匹配的电影</p>
            </div>
          </template>
          <MovieCard
            v-for="movie in store.movies"
            :key="movie.id"
            :movie="movie"
          />
        </div>

        <Pagination
          :current="store.page"
          :total="store.total"
          :page-size="store.pageSize"
          @change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMovieStore } from '@/stores/movies'
import { moviesApi, type RecommendItem } from '@/api/movies'
import { userApi, type FilterPacket } from '@/api/user'
import type { PlaylistBrief } from '@/types/movie'
import MovieCard from '@/components/common/MovieCard.vue'
import Pagination from '@/components/common/Pagination.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import { Search, Refresh, StarFilled, VideoCamera } from '@element-plus/icons-vue'

const router = useRouter()
const store = useMovieStore()
store.pageSize = 15

// ── 片单轮播 ──
const playlists = ref<PlaylistBrief[]>([])

// ── 搜索 ──
const keyword = ref("")
const selectedType = ref<number | undefined>(undefined)
const selectedRegion = ref<string | undefined>(undefined)
const selectedYear = ref<number | undefined>(undefined)
const selectedYearInput = ref('')
const selectedRating = ref<string | undefined>(undefined)
const filterPacket = ref<FilterPacket | null>(null)

// ── 猜你喜欢 ──
const recommendItems = ref<RecommendItem[]>([])
const recommendLoading = ref(false)
const recommendError = ref('')

// ── 片单 ──
async function loadPlaylists(): Promise<void> {
  try {
    const res = await userApi.playlists()
    playlists.value = res.data.items
  } catch {
    playlists.value = []
  }
}

// ── 猜你喜欢 ──
async function fetchRecommend(): Promise<void> {
  recommendLoading.value = true
  recommendError.value = ''
  try {
    const res = await moviesApi.recommend(10)
    recommendItems.value = res.data.items
  } catch {
    recommendItems.value = []
    recommendError.value = '加载推荐失败'
  } finally {
    recommendLoading.value = false
  }
}

// ── 搜索筛选 ──
function handleFilterChange(): void {
  let intervals = (filterPacket.value?.intervals ?? []).map((iv) => iv.interval_id)
  if (selectedRating.value) {
    intervals = [selectedRating.value]
  }
  store.setFilter(
    keyword.value,
    selectedType.value,
    intervals,
    selectedRegion.value,
    selectedYear.value,
  )
}

function handleYearChange(): void {
  const val = selectedYearInput.value.trim()
  selectedYear.value = val ? Number(val) || undefined : undefined
  handleFilterChange()
}

function handlePageChange(p: number): void {
  store.fetchList(p)
  loadPlaylists()
}

function handleSizeChange(s: number): void {
  store.pageSize = s
  store.fetchList(1)
}

onMounted(async () => {
  loadPlaylists()
  fetchRecommend()
  try {
    const res = await userApi.filterPacket()
    filterPacket.value = res.data
    const allIntervals = (res.data.intervals ?? []).map((iv) => iv.interval_id)
    store.setIntervalIds(allIntervals)
  } catch {
    filterPacket.value = null
  }
  await store.fetchList()
})
</script>

<style scoped>
.home-page {
  min-height: 100vh;
  background: #f5f7fa;
}

/* ═══ 左侧固定：猜你喜欢 ═══ */
.recommend-sidebar {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  padding: 24px 16px;
  position: fixed;
  top: 60px;
  left: 0;
  height: calc(100vh - 60px);
  overflow-y: auto;
  z-index: 10;
}

.recommend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 0 4px;
}

.section-title {
  font-size: 17px;
  color: #1a1a2e;
  margin: 0;
}

.recommend-list {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.recommend-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  cursor: pointer;
  transition: background 0.15s;
  border-radius: 8px;
  margin-bottom: 8px;
}

.recommend-item:last-child {
  margin-bottom: 0;
}

.recommend-item:hover {
  background: #f5f7fa;
}

.recommend-poster {
  width: 56px;
  height: 75px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ccc;
}

.recommend-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.recommend-info {
  flex: 1;
  min-width: 0;
}

.recommend-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recommend-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: #909399;
}

.recommend-rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #e8a838;
  font-weight: 500;
}

/* ═══ 右侧主内容区 ═══ */
.main-content {
  margin-left: 280px;
  min-width: 0;
  padding: 24px;
  max-width: 1600px;
}

/* ═══ 片单轮播 ═══ */
.playlist-carousel {
  margin-bottom: 20px;
  border-radius: 12px;
  overflow: hidden;
}

.carousel-item {
  width: 100%;
  height: 320px;
  background-size: cover;
  background-position: center;
  background-color: #2c3e50;
  cursor: pointer;
  display: flex;
  align-items: flex-end;
}

.carousel-overlay {
  width: 100%;
  padding: 24px 32px;
  background: linear-gradient(transparent, rgba(0,0,0,0.7));
  color: #fff;
}

.carousel-title {
  font-size: 22px;
  margin: 0 0 6px;
}

.carousel-desc {
  font-size: 14px;
  margin: 0;
  opacity: 0.85;
  line-height: 1.5;
  max-width: 600px;
}

.playlist-carousel-placeholder {
  background: #fff;
  border-radius: 12px;
  padding: 32px;
  margin-bottom: 20px;
}

/* ═══ 搜索栏 ═══ */
.home-filters {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  background: #fff;
  padding: 16px;
  border-radius: 12px;
}

.search-input {
  max-width: 360px;
  flex: 1;
}

.filter-select {
  width: 130px;
}

/* ═══ 影片列表 ═══ */
.movie-section {
  min-width: 0;
}

.movie-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 20px;
  min-height: 300px;
  background: #fff;
  padding: 20px;
  border-radius: 12px;
}

.movie-grid.is-empty {
  display: flex;
  justify-content: center;
  align-items: center;
}

.empty-state {
  text-align: center;
  color: #c0c4cc;
  padding: 48px 0;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}
</style>
