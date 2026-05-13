<template>
  <div class="home-page">
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
        @clear="handleSearch"
        @keyup.enter="handleSearch"
        @blur="handleSearch"
      />
      <el-select
        v-model="selectedType"
        placeholder="全部类型"
        clearable
        class="type-select"
        @change="handleTypeChange"
      >
        <el-option
          v-for="t in filterPacket?.types"
          :key="t.type_num"
          :label="t.type_name"
          :value="t.type_num"
        />
      </el-select>
    </div>

    <div class="rating-filters" v-if="filterPacket?.intervals?.length">
      <span class="rating-label">评分区间</span>
      <el-checkbox-group v-model="selectedIntervals" class="rating-checkbox-group">
        <el-checkbox
          v-for="iv in filterPacket.intervals"
          :key="iv.interval_id"
          :label="iv.interval_id"
          :value="iv.interval_id"
          @change="handleIntervalChange"
        >
          {{ iv.label }}
          <span class="interval-count">({{ iv.movie_count }})</span>
        </el-checkbox>
      </el-checkbox-group>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMovieStore } from '@/stores/movies'
import MovieCard from '@/components/common/MovieCard.vue'
import Pagination from '@/components/common/Pagination.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import { userApi, type FilterPacket } from '@/api/user'
import { Search } from '@element-plus/icons-vue'

const store = useMovieStore()

const keyword = ref('')
const selectedType = ref<number | undefined>(undefined)
const selectedIntervals = ref<string[]>([])
const filterPacket = ref<FilterPacket | null>(null)

onMounted(async () => {
  try {
    const res = await userApi.filterPacket()
    filterPacket.value = res.data
    selectedIntervals.value = (res.data.intervals ?? []).map((iv) => iv.interval_id)
    store.setIntervalIds(selectedIntervals.value)
  } catch {
    filterPacket.value = null
  }
  await store.fetchList()
})

function handleSearch(): void {
  store.setFilter(keyword.value, selectedType.value, selectedIntervals.value)
}

function handleTypeChange(): void {
  selectedIntervals.value = (filterPacket.value?.intervals ?? []).map((iv) => iv.interval_id)
  store.setFilter(keyword.value, selectedType.value, selectedIntervals.value)
}

function handleIntervalChange(): void {
  store.setFilter(keyword.value, selectedType.value, selectedIntervals.value)
}

function handlePageChange(p: number): void {
  store.fetchList(p)
}

function handleSizeChange(s: number): void {
  store.pageSize = s
  store.fetchList(1)
}
</script>

<style scoped>
.home-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px 24px;
}

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

.type-select {
  width: 160px;
}

.rating-filters {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  justify-content: center;
  flex-wrap: wrap;
}

.rating-label {
  font-size: 14px;
  color: #555;
  white-space: nowrap;
  font-weight: 500;
}

.rating-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  justify-content: center;
}

.rating-checkbox-group :deep(.el-checkbox) {
  margin-right: 0;
  height: 28px;
}

.interval-count {
  font-size: 12px;
  color: #aaa;
  margin-left: 2px;
}

.movie-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 20px;
  min-height: 200px;
}

.movie-grid.is-empty {
  display: flex;
  align-items: center;
  justify-content: center;
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
</style>
