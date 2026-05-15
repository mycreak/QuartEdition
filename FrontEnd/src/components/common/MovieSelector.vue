<template>
  <el-dialog
    v-model="visible"
    title="选择电影"
    width="800px"
    @close="handleClose"
  >
    <!-- 筛选栏 - 已优化间距和布局 -->
    <div class="cus_space-between">
      <!-- 左边：所有筛选控件 - 间距从12px提升到16px，更宽松 -->
      <div class="flex flex-wrap items-center gap-4">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索片名 / douban_id..."
          clearable
          style="width: 200px"
          @keyup.enter="fetchMovies(1)"
        />
        <el-select
          v-model="filters.type_num"
          placeholder="类型"
          clearable
          style="width: 100px"
          @change="fetchMovies(1)"
        >
          <el-option
            v-for="t in typeOptions"
            :key="t.type_num"
            :label="`${t.type_name} (${t.type_num})`"
            :value="t.type_num"
          />
        </el-select>
        <el-input
          v-model="filters.release_year"
          placeholder="年份"
          clearable
          style="width: 100px"
          maxlength="4"
          @keyup.enter="fetchMovies(1)"
        />
        <el-select
          v-model="filters.region_id"
          placeholder="地区"
          clearable
          style="width: 100px"
          @change="fetchMovies(1)"
        >
          <el-option
            v-for="r in allRegions"
            :key="r.id"
            :label="r.name"
            :value="r.id"
          />
        </el-select>
        <el-select
          v-model="filters.interval_ids"
          placeholder="评分"
          clearable
          style="width: 100px"
          @change="fetchMovies(1)"
        >
          <el-option label="9分及以上" value="100:90" />
          <el-option label="8-9分" value="90:80" />
          <el-option label="7-8分" value="80:70" />
          <el-option label="6-7分" value="70:60" />
          <el-option label="6分以下" value="60:0" />
        </el-select>
      </div>

      <!-- 右边：操作按钮 - 固定在最右侧，按钮间距调整为12px -->
      <div class="items-center gap-2">
        <el-button @click="handleReset">重置</el-button>
        <el-button type="primary" @click="fetchMovies(1)" :loading="loading">
          搜索
        </el-button>
      </div>
    </div>

    <!-- 电影列表 -->
    <el-table
      :data="movieList"
      v-loading="loading"
      @row-click="handleRowClick"
      stripe
      height="400px"
      highlight-current-row
    >
      <el-table-column prop="title" label="电影名" min-width="200" show-overflow-tooltip />
      <el-table-column prop="douban_id" label="豆瓣ID" width="120" />
      <el-table-column label="类型" min-width="120">
        <template #default="{ row }">
          <el-tag size="small" v-for="g in row.genres" :key="g" class="mr-1">
            {{ TYPE_MAP[Number(g)] || g }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="地区" min-width="100">
        <template #default="{ row }">
          <el-tag size="small" v-for="r in row.regions" :key="r.id" class="mr-1">
            {{ r.name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="release_year" label="年份" width="80" />
      <el-table-column label="评分" width="80">
        <template #default="{ row }">
          <span class="rating-text">{{ row.rating?.average ?? '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-bar mt-4 flex justify-end">
      <el-pagination
        v-model:current-page="currentPage"
        :total="total"
        :page-size="pageSize"
        background
        layout="total, prev, pager, next"
        @current-change="fetchMovies"
      />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="handleConfirm" :disabled="!selectedMovie">
          确认选择
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { adminMoviesApi } from '@/api/admin/movies'
import client from '@/api/client'
import type { Movie } from '@/types/movie'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'select', movie: Movie): void
}>()

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

const visible = ref(false)
const loading = ref(false)
const movieList = ref<Movie[]>([])
const selectedMovie = ref<Movie | null>(null)
const currentPage = ref(1)
const total = ref(0)
const pageSize = ref(20)

const filters = ref({
  keyword: '',
  type_num: undefined as number | undefined,
  release_year: undefined as number | undefined,
  region_id: undefined as number | undefined,
  interval_ids: ''
})

const allRegions = ref<{ id: number; name: string }[]>([])

async function fetchAllRegions() {
  try {
    const res = await client.get<{ id: number; name: string }[]>('/admin/regions')
    allRegions.value = res.data || []
  } catch {
    // 地区加载失败不影响主体功能
  }
}

async function fetchMovies(page = 1) {
  loading.value = true
  try {
    const params = {
      page,
      page_size: pageSize.value,
      keyword: filters.value.keyword || undefined,
      type_num: filters.value.type_num,
      release_year: filters.value.release_year,
      region_id: filters.value.region_id,
      interval_ids: filters.value.interval_ids || undefined,
      published: 1
    }
    const res = await adminMoviesApi.list(params)
    movieList.value = res.data.items
    total.value = res.data.total
    currentPage.value = page
  } finally {
    loading.value = false
  }
}

// 重置筛选参数
function handleReset() {
  filters.value = {
    keyword: '',
    type_num: undefined,
    release_year: undefined,
    region_id: undefined,
    interval_ids: ''
  }
  fetchMovies(1)
}

// 行点击
function handleRowClick(row: Movie) {
  selectedMovie.value = row
}

// 确认选择
function handleConfirm() {
  if (selectedMovie.value) {
    emit('select', selectedMovie.value)
    handleClose()
  }
}

// 关闭弹窗
function handleClose() {
  emit('update:modelValue', false)
  // 重置状态
  selectedMovie.value = null
  filters.value = {
    keyword: '',
    type_num: undefined,
    release_year: undefined,
    region_id: undefined,
    interval_ids: ''
  }
  currentPage.value = 1
}

// 监听弹窗显示
watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val) {
    fetchMovies(1)
  }
}, { immediate: true })

onMounted(() => {
  fetchAllRegions()
})
</script>

<style scoped>
.filter-bar {
  align-items: center;
}

.cus_space-between {
  display: flex;
  justify-content: space-between;
}

.rating-text {
  color: #f56c6c;
  font-weight: bold;
}

/* 选中行高亮样式更明显 */
:deep(.el-table__row.current-row) {
  background-color: #ecf5ff !important;
}
</style>
