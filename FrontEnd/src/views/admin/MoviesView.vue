<template>
  <div class="admin-movies">
    <h2 class="page-title">电影管理</h2>

    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索片名 / douban_id..." clearable class="search-input" />
      <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select" style="width: 140px">
        <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
      </el-select>
      <el-input v-model="yearFilter" placeholder="年份" clearable class="year-input" maxlength="4" />
      <el-select v-model="regionFilter" placeholder="全部国家/地区" clearable class="filter-select" style="width: 150px">
        <el-option v-for="r in allRegions" :key="r.id" :label="r.name" :value="r.id" />
      </el-select>
      <el-select v-model="publishedFilter" placeholder="上下架" clearable class="filter-select">
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
import client from '@/api/client'
import type { Movie } from '@/types/movie'

const router = useRouter()
const authStore = useAuthStore()
const movies = ref<Movie[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const typeFilter = ref<number | undefined>(undefined)
const yearFilter = ref('')
const regionFilter = ref<number | undefined>(undefined)
const publishedFilter = ref('')
const allRegions = ref<{ id: number; name: string }[]>([])

const TYPE_MAP: Record<number, string> = {
  1: '纪录片', 2: '传记', 3: '犯罪', 4: '历史', 5: '动作',
  6: '情色', 7: '歌舞', 8: '儿童', 10: '悬疑', 11: '剧情',
  12: '灾难', 13: '爱情', 14: '音乐', 15: '冒险', 16: '奇幻',
  17: '科幻', 18: '运动', 19: '惊悚', 20: '恐怖', 22: '战争',
  23: '短片', 24: '喜剧', 25: '动画', 27: '西部', 28: '家庭',
  29: '武侠', 30: '古装', 31: '黑色电影',
}

const typeOptions = Object.entries(TYPE_MAP).map(
  ([num, name]) => ({ type_num: Number(num), type_name: name })
)

let timer: ReturnType<typeof setTimeout> | null = null

async function fetchAllRegions() {
  try {
    const res = await client.get<{ id: number; name: string }[]>('/admin/regions')
    allRegions.value = res.data || []
  } catch {
    ElMessage.error('加载地区列表失败')
  }
}

async function fetchList(p = 1) {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (typeFilter.value) params.type_num = typeFilter.value
    if (yearFilter.value) {
      const y = parseInt(yearFilter.value, 10)
      if (!isNaN(y)) params.release_year = y
    }
    if (regionFilter.value !== undefined) params.region_id = regionFilter.value
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

watch(typeFilter, () => fetchList(1))
watch(yearFilter, () => fetchList(1))
watch(regionFilter, () => fetchList(1))
watch(publishedFilter, () => fetchList(1))

onMounted(async () => {
  await fetchAllRegions()
  fetchList()
})
</script>

<style scoped>
.admin-movies { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.search-input { width: 280px; }
.filter-select { width: 120px; }
.year-input { width: 100px; }
.rating-cell { color: #e8a838; font-weight: 600; }
.rating-count { font-size: 11px; color: #aaa; }
.genre-tag { margin-right: 4px; margin-bottom: 2px; }
.c-gray { color: #c0c4cc; }
.paginator { margin-top: 16px; justify-content: flex-end; }
</style>
