<template>
  <div class="admin-movies">
    <h2 class="page-title">电影管理</h2>

    <!-- 有管理权限显示tab -->
    <el-tabs v-model="activeTab" class="movie-tabs" v-if="authStore.checkPermission('movie:manage')">
      <!-- 电影列表tab -->
      <el-tab-pane label="电影列表" name="movies">
        <div class="toolbar">
          <el-input v-model="keyword" placeholder="搜索片名 / douban_id..." clearable class="search-input" />
          <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select" style="width: 140px">
            <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
          </el-select>
          <el-input v-model="yearFilter" placeholder="年份" clearable class="year-input" maxlength="4" @blur="onYearFilterChange" @keyup.enter="onYearFilterChange" />
          <el-select v-model="regionFilter" placeholder="全部国家/地区" clearable class="filter-select" style="width: 150px">
            <el-option v-for="r in allRegions" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
          <el-select v-model="ratingFilter" placeholder="全部评分" clearable class="filter-select" style="width: 130px">
            <el-option label="9分及以上" value="100:90" />
            <el-option label="8-9分" value="90:80" />
            <el-option label="7-8分" value="80:70" />
            <el-option label="6-7分" value="70:60" />
            <el-option label="6分以下" value="60:0" />
          </el-select>
          <el-select v-model="publishedFilter" placeholder="上下架" clearable class="filter-select">
            <el-option label="已上架" value="published" />
            <el-option label="已下架" value="unpublished" />
          </el-select>
        </div>

        <el-table :data="movies" stripe v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="douban_id" label="豆瓣ID" width="100" />
          <el-table-column prop="title" label="片名" min-width="200" />
          <el-table-column label="类型" min-width="140">
            <template #default="{ row }">
              <el-tag v-for="g in (row.genres || [])" :key="g" size="small" class="genre-tag">{{ g }}</el-tag>
              <span v-if="!row.genres?.length" class="c-gray">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="release_year" label="年份" width="80" />
          <el-table-column label="地区" min-width="140">
            <template #default="{ row }">
              <el-tag v-for="r in (row.regions || [])" :key="r.id" size="small" class="genre-tag">{{ r.name }}</el-tag>
              <span v-if="!row.regions?.length" class="c-gray">—</span>
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
      </el-tab-pane>

      <!-- 重名人员管理tab -->
      <el-tab-pane label="重名人员管理" name="duplicate">
        <div class="toolbar">
          <el-button type="primary" @click="refreshDuplicateList" :loading="duplicateLoading">刷新列表</el-button>
        </div>

        <el-table :data="duplicateList" stripe v-loading="duplicateLoading">
          <el-table-column prop="name" label="重名姓名" width="150" />
          <el-table-column label="人员1" min-width="200">
            <template #default="{ row }">
              <span>{{ row.person_name1 }} (ID: {{ row.person_id1 }})</span>
            </template>
          </el-table-column>
          <el-table-column label="人员2" min-width="200">
            <template #default="{ row }">
              <span>{{ row.person_name2 }} (ID: {{ row.person_id2 }})</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="发现时间" width="180" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDuplicateDetail(row)">查看关联电影</el-button>
              <el-button size="small" type="warning" link @click="openHandleDialog(row)">处理</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination class="paginator" v-model:current-page="duplicatePage" :total="duplicateTotal" :page-size="duplicatePageSize" background layout="total, prev, pager, next" @current-change="fetchDuplicateList" />
      </el-tab-pane>
    </el-tabs>

    <!-- 无管理权限直接显示电影列表 -->
    <template v-else>
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索片名 / douban_id..." clearable class="search-input" />
        <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select" style="width: 140px">
          <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
        </el-select>
        <el-input v-model="yearFilter" placeholder="年份" clearable class="year-input" maxlength="4" />
        <el-select v-model="regionFilter" placeholder="全部国家/地区" clearable class="filter-select" style="width: 150px">
          <el-option v-for="r in allRegions" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-select v-model="ratingFilter" placeholder="全部评分" clearable class="filter-select" style="width: 130px">
          <el-option label="9分及以上" value="100:90" />
          <el-option label="8-9分" value="90:80" />
          <el-option label="7-8分" value="80:70" />
          <el-option label="6-7分" value="70:60" />
          <el-option label="6分以下" value="60:0" />
        </el-select>
        <el-select v-model="publishedFilter" placeholder="上下架" clearable class="filter-select">
          <el-option label="已上架" value="published" />
          <el-option label="已下架" value="unpublished" />
        </el-select>
      </div>

      <el-table :data="movies" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="douban_id" label="豆瓣ID" width="100" />
        <el-table-column prop="title" label="片名" min-width="200" />
        <el-table-column label="类型" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="g in (row.genres || [])" :key="g" size="small" class="genre-tag">{{ g }}</el-tag>
            <span v-if="!row.genres?.length" class="c-gray">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="release_year" label="年份" width="80" />
        <el-table-column label="地区" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="r in (row.regions || [])" :key="r.id" size="small" class="genre-tag">{{ r.name }}</el-tag>
            <span v-if="!row.regions?.length" class="c-gray">—</span>
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
    </template>

    <!-- 重名人员详情弹窗 -->
    <el-dialog v-model="detailVisible" title="重名人员关联电影对比" width="1200px" destroy-on-close>
      <el-row :gutter="20">
        <el-col :span="12">
          <h4 style="margin-bottom: 12px;">
            人员：{{ currentDuplicate?.person_name1 }} (ID: {{ currentDuplicate?.person_id1 }})
            <span style="color: #909399; font-size: 14px; margin-left: 10px;">共 {{ person1Movies.length }} 部电影</span>
          </h4>
          <el-table :data="person1Movies" stripe v-loading="person1Loading" height="400">
            <el-table-column prop="title" label="电影名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="year" label="年份" width="80" />
            <el-table-column label="地区" min-width="150">
              <template #default="{ row }">
                <el-tag v-for="r in row.regions" :key="r" size="small" style="margin-bottom: 2px;">{{ r }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="role_type" label="角色" width="100" />
          </el-table>
        </el-col>
        <el-col :span="12">
          <h4 style="margin-bottom: 12px;">
            人员：{{ currentDuplicate?.person_name2 }} (ID: {{ currentDuplicate?.person_id2 }})
            <span style="color: #909399; font-size: 14px; margin-left: 10px;">共 {{ person2Movies.length }} 部电影</span>
          </h4>
          <el-table :data="person2Movies" stripe v-loading="person2Loading" height="400">
            <el-table-column prop="title" label="电影名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="year" label="年份" width="80" />
            <el-table-column label="地区" min-width="150">
              <template #default="{ row }">
                <el-tag v-for="r in row.regions" :key="r" size="small" style="margin-bottom: 2px;">{{ r }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="role_type" label="角色" width="100" />
          </el-table>
        </el-col>
      </el-row>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="warning" @click="openHandleDialog(currentDuplicate)">去处理</el-button>
      </template>
    </el-dialog>

    <!-- 重名处理弹窗 -->
    <el-dialog v-model="handleVisible" title="处理重名人员" width="600px" destroy-on-close>
      <div style="padding: 20px 0;">
        <p>待处理重名：<strong>{{ currentDuplicate?.name }}</strong></p>
        <p>人员A：{{ currentDuplicate?.person_name1 }} (ID: {{ currentDuplicate?.person_id1 }})</p>
        <p>人员B：{{ currentDuplicate?.person_name2 }} (ID: {{ currentDuplicate?.person_id2 }})</p>
        <el-divider />
        <p style="color: #606266;">请判断两人是否为同一人：</p>
      </div>
      <template #footer>
        <el-button @click="handleVisible = false">取消</el-button>
        <el-button type="info" @click="confirmNotSame" :loading="confirmLoading">不是同一人</el-button>
        <el-button type="primary" @click="openMergeDialog">合并为同一人</el-button>
      </template>
    </el-dialog>

    <!-- 合并人员确认弹窗 -->
    <el-dialog v-model="mergeVisible" title="确认合并人员" width="550px" destroy-on-close>
      <p style="margin-bottom: 20px;">合并后，废弃人员的所有电影关联将迁移到保留人员，废弃人员将被标记为无效，操作不可逆，请谨慎选择：</p>
      <el-radio-group v-model="keepPersonId" style="margin: 20px 0; padding-left: 20px;">
        <el-radio :label="currentDuplicate?.person_id1" style="margin-bottom: 10px;">
          保留：<strong>{{ currentDuplicate?.person_name1 }}</strong> (ID: {{ currentDuplicate?.person_id1 }})
          <span style="color: #909399; font-size: 12px; margin-left: 10px;">（废弃：{{ currentDuplicate?.person_name2 }}）</span>
        </el-radio>
        <el-radio :label="currentDuplicate?.person_id2">
          保留：<strong>{{ currentDuplicate?.person_name2 }}</strong> (ID: {{ currentDuplicate?.person_id2 }})
          <span style="color: #909399; font-size: 12px; margin-left: 10px;">（废弃：{{ currentDuplicate?.person_name1 }}）</span>
        </el-radio>
      </el-radio-group>
      <p style="color: #f56c6c; margin-top: 20px; padding: 10px; background: #fef0f0; border-radius: 4px;">⚠️ 警告：合并操作无法撤销，请确认选择正确！</p>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitMerge" :loading="mergeLoading" :disabled="keepPersonId === null">确认合并</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
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
const ratingFilter = ref('')
const allRegions = ref<{ id: number; name: string }[]>([])

// 重名人员管理相关变量
const activeTab = ref('movies')
const duplicateList = ref<{ id: number; name: string; person_id1: number; person_name1: string; person_id2: number; person_name2: string; created_at: string }[]>([])
const duplicateTotal = ref(0)
const duplicatePage = ref(1)
const duplicatePageSize = ref(20)
const duplicateLoading = ref(false)

// 弹窗相关变量
const detailVisible = ref(false)
const handleVisible = ref(false)
const mergeVisible = ref(false)
const currentDuplicate = ref<{ id: number; name: string; person_id1: number; person_name1: string; person_id2: number; person_name2: string } | null>(null)
const person1Movies = ref<{ movie_id: number; title: string; poster: string; year: number; regions: string[]; role_type: string }[]>([])
const person2Movies = ref<{ movie_id: number; title: string; poster: string; year: number; regions: string[]; role_type: string }[]>([])
const person1Loading = ref(false)
const person2Loading = ref(false)
const confirmLoading = ref(false)
const mergeLoading = ref(false)
const keepPersonId = ref<number | null>(null)

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
    if (ratingFilter.value) params.interval_ids = ratingFilter.value
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

// ==================== 重名人员管理相关方法 ====================
async function fetchDuplicateList(p = 1) {
  duplicateLoading.value = true
  try {
    const res = await client.get<{ items: any[]; total: number }>('/admin/duplicate-persons', {
      params: { page: p, page_size: duplicatePageSize.value }
    })
    duplicateList.value = res.data.items
    duplicateTotal.value = res.data.total
    duplicatePage.value = p
  } catch {
    ElMessage.error('加载重名列表失败')
  } finally {
    duplicateLoading.value = false
  }
}

function refreshDuplicateList() {
  fetchDuplicateList(1)
}

async function viewDuplicateDetail(row: any) {
  currentDuplicate.value = row
  detailVisible.value = true
  person1Loading.value = true
  person2Loading.value = true
  
  try {
    // 并行请求两个人的关联电影
    const [res1, res2] = await Promise.all([
      client.get<{ items: any[] }>(`/admin/duplicate-persons/${row.person_id1}/movies`),
      client.get<{ items: any[] }>(`/admin/duplicate-persons/${row.person_id2}/movies`)
    ])
    person1Movies.value = res1.data.items
    person2Movies.value = res2.data.items
  } catch {
    ElMessage.error('加载人员关联电影失败')
  } finally {
    person1Loading.value = false
    person2Loading.value = false
  }
}

function openHandleDialog(row: any) {
  currentDuplicate.value = row
  handleVisible.value = true
}

async function confirmNotSame() {
  if (!currentDuplicate.value) return
  // 二次确认
  try {
    await ElMessageBox.confirm(
      `确认【${currentDuplicate.value.person_name1}】和【${currentDuplicate.value.person_name2}】不是同一人吗？确认后两人将被标记为正常，不再出现在重名列表中。`,
      '确认处理',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  confirmLoading.value = true
  try {
    await client.post('/admin/duplicate-persons/confirm-not-same', {
      duplicate_id: currentDuplicate.value.id,
      person_id1: currentDuplicate.value.person_id1,
      person_id2: currentDuplicate.value.person_id2
    })
    ElMessage.success('处理成功')
    handleVisible.value = false
    fetchDuplicateList() // 刷新列表
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '处理失败，请稍后重试')
  } finally {
    confirmLoading.value = false
  }
}

function openMergeDialog() {
  keepPersonId.value = null
  mergeVisible.value = true
}

async function submitMerge() {
  if (!currentDuplicate.value || keepPersonId.value === null) {
    ElMessage.warning('请选择要保留的人员')
    return
  }
  // 计算要废弃的人员ID
  const discardPersonId = keepPersonId.value === currentDuplicate.value.person_id1 
    ? currentDuplicate.value.person_id2 
    : currentDuplicate.value.person_id1
  const keepName = keepPersonId.value === currentDuplicate.value.person_id1 ? currentDuplicate.value.person_name1 : currentDuplicate.value.person_name2
  const discardName = keepPersonId.value === currentDuplicate.value.person_id1 ? currentDuplicate.value.person_name2 : currentDuplicate.value.person_name1

  // 二次确认
  try {
    await ElMessageBox.confirm(
      `确认合并吗？合并后【${discardName}】将被标记为无效，所有关联的电影都会迁移到【${keepName}】，操作不可逆！`,
      '确认合并',
      { type: 'warning', confirmButtonText: '确认合并', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  mergeLoading.value = true
  try {
    await client.post('/admin/duplicate-persons/merge', {
      duplicate_id: currentDuplicate.value.id,
      keep_person_id: keepPersonId.value,
      discard_person_id: discardPersonId
    })
    ElMessage.success('合并成功')
    mergeVisible.value = false
    handleVisible.value = false
    fetchDuplicateList() // 刷新列表
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '合并失败，请稍后重试')
  } finally {
    mergeLoading.value = false
  }
}

watch(keyword, () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => fetchList(1), 300)
})

// 监听tab切换，切换到重名管理时加载列表
watch(activeTab, (newVal) => {
  if (newVal === 'duplicate' && duplicateList.value.length === 0) {
    fetchDuplicateList()
  }
})

watch(typeFilter, () => fetchList(1))
// 年份筛选失焦/回车时触发查询
function onYearFilterChange() {
  fetchList(1)
}
watch(regionFilter, () => fetchList(1))
watch(publishedFilter, () => fetchList(1))
watch(ratingFilter, () => fetchList(1))

onMounted(async () => {
  await fetchAllRegions()
  fetchList()
})
</script>

<style scoped>
.admin-movies { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.movie-tabs { margin-bottom: 20px; }
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
