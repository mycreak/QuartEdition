<template>
  <div class="home-page">

    <!-- ── Tab 切换 ── -->
    <el-tabs v-model="activeTab" class="home-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="推荐" name="recommend" />
      <el-tab-pane label="搜索" name="search" />
    </el-tabs>

    <!-- ═══════════════════════════════════════════════════════════
         推荐 Tab
         ═══════════════════════════════════════════════════════════ -->
    <template v-if="activeTab === 'recommend'">
      <!-- ── 片单轮播 ── -->
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
        <el-empty description="片单轮播 — 管理员发布后展示" :image-size="80" />
      </div>

      <el-divider />

      <!-- ── 猜你喜欢 ── -->
      <div class="recommend-header">
        <h2 class="section-title">猜你喜欢</h2>
        <el-button :icon="Refresh" :loading="recommendLoading" @click="fetchRecommend">
          刷新
        </el-button>
      </div>

      <div v-loading="recommendLoading" class="movie-grid" :class="{ 'is-empty': !recommendLoading && !recommendItems.length }">
        <template v-if="!recommendLoading && !recommendItems.length && !recommendError">
          <div class="empty-state">
            <el-icon :size="48"><Search /></el-icon>
            <p>暂无推荐数据</p>
          </div>
        </template>
        <ErrorAlert :message="recommendError" @close="recommendError = ''" class="mb-4" />
        <MovieCard
          v-for="item in recommendItems"
          :key="item.movie_id"
          :movie="{ id: item.movie_id, douban_id: item.douban_id, title: item.title, poster_url: item.poster_url, release_year: item.release_year, rating: item.rating ? { average: item.rating, count: 0 } : undefined, genres: [] }"
        />
      </div>
    </template>

    <!-- ═══════════════════════════════════════════════════════════
         搜索 Tab
         ═══════════════════════════════════════════════════════════ -->
    <template v-else>
      <div class="home-hero">
        <h1 class="home-title">电影数据库</h1>
        <p class="home-subtitle">浏览豆瓣电影数据，发现精彩影片</p>
      </div>

      <div class="home-filters">
        <el-input
          v-model="keyword"
          placeholder="搜索电影名称..."
          :prefix-icon="Search"
          clearable
          class="search-input"
          @clear="handleFilterChange"
          @keyup.enter="handleFilterChange"
          @blur="handleFilterChange"
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
           placeholder="输入年份"
           clearable
           class="filter-select"
           @change="handleYearChange"
           @clear="selectedYear = undefined; handleFilterChange()"
         />
        <el-select
          v-model="selectedRating"
          placeholder="全部评分"
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
    </template>
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
import { Search, Refresh } from '@element-plus/icons-vue'

const router = useRouter()
const store = useMovieStore()
store.pageSize = 15

// ── 轮播 ──
const playlists = ref<PlaylistBrief[]>([])

// ── 搜索 tab 状态 ──
const keyword = ref("")
const selectedType = ref<number | undefined>(undefined)
const selectedRegion = ref<string | undefined>(undefined)
const selectedYear = ref<number | undefined>(undefined)
const selectedYearInput = ref('')
const selectedRating = ref<string | undefined>(undefined)
const filterPacket = ref<FilterPacket | null>(null)

// ── 推荐 tab 状态 ──
const activeTab = ref('recommend')
const recommendItems = ref<RecommendItem[]>([])
const recommendLoading = ref(false)
const recommendError = ref('')

// ── 推荐 ──
async function loadPlaylists(): Promise<void> {
  try {
    const res = await userApi.playlists()
    playlists.value = res.data.items
  } catch {
    playlists.value = []
  }
}

async function fetchRecommend(): Promise<void> {
  recommendLoading.value = true
  recommendError.value = ''
  try {
    const res = await moviesApi.recommend(10)
    recommendItems.value = res.data.items
  } catch {
    recommendItems.value = []
    recommendError.value = '加载推荐失败，请稍后重试'
  } finally {
    recommendLoading.value = false
  }
}

// ── 搜索 ──
onMounted(async () => {
  // 片单轮播
  loadPlaylists()
  // 推荐 Tab 初始加载
  if (activeTab.value === 'recommend') {
    fetchRecommend()
  }
  // 搜索 Tab 数据
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
}

function handleSizeChange(s: number): void {
  store.pageSize = s
  store.fetchList(1)
}

function handleTabChange(name: string | number): void {
  if (name === 'recommend' && !recommendItems.value.length) {
    fetchRecommend()
  }
}
</script>

<style scoped>
.home-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 24px;
}

.home-tabs {
  margin-bottom: 24px;
}

/* ── 推荐 ── */
.playlist-carousel {
  margin-bottom: 24px;
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
  background: #f5f7fa;
  border-radius: 12px;
  padding: 32px;
  margin-bottom: 8px;
}

.recommend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  font-size: 20px;
  color: #1a1a2e;
  margin: 0;
}

/* ── 搜索 ── */
.home-hero {
  text-align: center;
  margin-bottom: 32px;
}

.home-title {
  font-size: 28px;
  color: #1a1a2e;
  margin: 0 0 8px;
}

.home-subtitle {
  font-size: 15px;
  color: #888;
  margin: 0;
}

.home-filters {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  justify-content: center;
}

.search-input {
  max-width: 360px;
  flex: 1;
}

.filter-select {
  width: 130px;
}

.movie-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 20px;
  min-height: 300px;
  max-width: 1100px;
  margin: 0 auto;
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

.mb-4 {
  margin-bottom: 16px;
}
</style>
