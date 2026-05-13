<template>
  <div class="admin-movies">
    <h2 class="page-title">电影管理</h2>

    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索电影..." clearable class="search-input" />
      <el-select v-model="publishedFilter" placeholder="上下架" clearable>
        <el-option label="已上架" value="published" />
        <el-option label="已下架" value="unpublished" />
      </el-select>
    </div>

    <el-table :data="movies" stripe v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="片名" min-width="200" />
      <el-table-column prop="release_year" label="年份" width="80" />
      <el-table-column label="类型" min-width="140">
        <template #default="{ row }">
          <el-tag v-for="g in (row.genres || [])" :key="g" size="small" class="genre-tag">{{ g }}</el-tag>
          <span v-if="!row.genres?.length" class="c-gray">—</span>
        </template>
      </el-table-column>
      <el-table-column label="评分" width="100">
        <template #default="{ row }">
          <span class="rating-cell">{{ row.rating?.average?.toFixed(1) || '-' }}</span>
          <span class="rating-count" v-if="row.rating?.count">({{ row.rating.count }})</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_published ? 'success' : 'info'" size="small">{{ row.is_published ? '已上架' : '已下架' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
          <el-button v-if="authStore.checkPermission('movie:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="togglePublish(row)">
            {{ row.is_published ? '下架' : '上架' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="paginator" v-model:current-page="page" :total="total" :page-size="pageSize" background layout="total, prev, pager, next" @current-change="fetchList" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminMoviesApi } from '@/api/admin/movies'
import type { Movie } from '@/types/movie'

const router = useRouter()
const authStore = useAuthStore()
const movies = ref<Movie[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const publishedFilter = ref('')

let timer: ReturnType<typeof setTimeout> | null = null

async function fetchList(p = 1) {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (publishedFilter.value === 'published') params.published = 1
    else if (publishedFilter.value === 'unpublished') params.published = 0
    const res = await adminMoviesApi.list(params as any)
    movies.value = res.data.items
    total.value = res.data.total
    page.value = p
  } catch { /* ignore */ } finally { loading.value = false }
}

function viewDetail(row: Movie) {
  router.push(`/admin/movies/${row.id}`)
}

async function togglePublish(row: Movie) {
  try {
    const api = row.is_published ? adminMoviesApi.unpublish : adminMoviesApi.publish
    await api(row.id)
    row.is_published = !row.is_published
    ElMessage.success(row.is_published ? '已上架' : '已下架')
  } catch { ElMessage.error('操作失败') }
}

watch(keyword, () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => fetchList(1), 300)
})

watch(publishedFilter, () => fetchList(1))

onMounted(() => fetchList())
</script>

<style scoped>
.admin-movies { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.search-input { width: 240px; }
.rating-cell { color: #e8a838; font-weight: 600; }
.rating-count { font-size: 11px; color: #aaa; }
.genre-tag { margin-right: 4px; margin-bottom: 2px; }
.c-gray { color: #c0c4cc; }
.paginator { margin-top: 16px; justify-content: flex-end; }
</style>
