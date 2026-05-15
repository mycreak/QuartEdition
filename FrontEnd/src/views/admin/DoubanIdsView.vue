<template>
  <div class="douban-ids-page">
    <h2 class="page-title">豆瓣电影 ID 资产管理</h2>

    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索 ID 或电影名" clearable style="width: 220px" @input="onSearch" />
      <el-select v-model="filterType" placeholder="类型过滤" clearable style="width: 170px" @change="fetchList(1)">
        <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
      </el-select>
      <el-select v-model="filterInterval" placeholder="评分区间" clearable style="width: 160px" @change="fetchList(1)">
        <el-option v-for="iv in intervalOptions" :key="iv.interval_id" :label="iv.label" :value="iv.interval_id" />
      </el-select>
      <el-radio-group v-model="filterAcquired" @change="fetchList(1)">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="0">未认领</el-radio-button>
        <el-radio-button value="1">已认领</el-radio-button>
      </el-radio-group>
      <el-button type="primary" @click="openAdd" class="ml-a">添加 ID</el-button>
    </div>

    <el-table :data="items" stripe v-loading="loading">
      <el-table-column prop="douban_id" label="豆瓣 ID" width="120" />
      <el-table-column prop="title" label="电影名" min-width="160" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          {{ row.type_num != null ? (TYPE_MAP[row.type_num] || row.type_num) : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="评分区间" width="100">
        <template #default="{ row }">
          {{ row.interval_id || '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="70">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source === 'manual' ? 'warning' : 'info'">{{ row.source === 'manual' ? '手动' : 'API' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.is_scraped" size="small" type="success">已完成</el-tag>
          <el-tag v-else-if="row.is_acquired" size="small" type="warning">已认领</el-tag>
          <el-tag v-else size="small" type="info">未认领</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="认领人" width="100">
        <template #default="{ row }">
          {{ row.claimed_by_name || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.is_acquired && !row.is_scraped" size="small" type="primary" link @click="acquire(row)">认领</el-button>
          <el-button v-else-if="row.is_acquired && !row.is_scraped && row.admin_id === currentUserId" size="small" type="warning" link @click="release(row)">释放</el-button>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="paginator" v-model:current-page="page" :total="total" :page-size="pageSize" background layout="total, prev, pager, next" @current-change="fetchList" />

    <el-dialog v-model="addVisible" title="手动添加豆瓣电影 ID" width="450px">
      <el-form :model="addForm" label-position="top">
        <el-form-item label="豆瓣电影 ID（douban_id）">
          <el-input v-model="addForm.douban_id" placeholder="如 1292052" />
        </el-form-item>
        <el-form-item label="电影名">
          <el-input v-model="addForm.title" placeholder="如 肖申克的救赎" />
        </el-form-item>
        <el-form-item label="豆瓣类型">
          <el-select v-model="addForm.type_num" placeholder="选择类型" style="width: 100%">
            <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
          </el-select>
        </el-form-item>
        <el-form-item label="评分区间">
          <el-select v-model="addForm.interval_id" placeholder="选择评分区间" style="width: 100%">
            <el-option v-for="iv in intervalOptions" :key="iv.interval_id" :label="iv.label" :value="iv.interval_id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAdd" :loading="addLoading">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminDoubanIdsApi, type DoubanId } from '@/api/admin/douban_ids'

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

const intervalOptions = [
  { interval_id: '100:90', label: '9.0~10.0' },
  { interval_id: '90:80', label: '8.0~9.0' },
  { interval_id: '80:70', label: '7.0~8.0' },
  { interval_id: '70:60', label: '6.0~7.0' },
  { interval_id: '60:50', label: '5.0~6.0' },
  { interval_id: '50:40', label: '4.0~5.0' },
  { interval_id: '40:30', label: '3.0~4.0' },
  { interval_id: '30:20', label: '2.0~3.0' },
  { interval_id: '20:10', label: '1.0~2.0' },
  { interval_id: '10:0', label: '0~1.0' },
]

const authStore = useAuthStore()
const currentUserId = computed(() => authStore.user?.id ?? 0)

const items = ref<DoubanId[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const filterType = ref<number | ''>('')
const filterInterval = ref('')
const filterAcquired = ref('')
const addVisible = ref(false)
const addLoading = ref(false)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const addForm = reactive({ douban_id: '', title: '', type_num: null as number | null, interval_id: '' })

async function fetchList(p = 1) {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (filterType.value !== '') params.type_num = filterType.value
    if (filterInterval.value) params.interval_id = filterInterval.value
    if (filterAcquired.value) params.is_acquired = filterAcquired.value
    const res = await adminDoubanIdsApi.list(params as any)
    items.value = res.data.items
    total.value = res.data.total
    page.value = p
  } catch { /* ignore */ } finally { loading.value = false }
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => fetchList(1), 300)
}

function openAdd() {
  addForm.douban_id = ''
  addForm.title = ''
  addForm.type_num = null
  addForm.interval_id = ''
  addVisible.value = true
}

async function submitAdd() {
  addLoading.value = true
  try {
    await adminDoubanIdsApi.add({
      douban_id: addForm.douban_id,
      title: addForm.title,
      type_num: addForm.type_num ?? undefined,
      interval_id: addForm.interval_id || undefined,
    })
    ElMessage.success(`已添加 ${addForm.douban_id}`)
    addVisible.value = false
    await fetchList(1)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '添加失败')
  } finally { addLoading.value = false }
}

async function acquire(row: DoubanId) {
  try {
    await ElMessageBox.confirm(
      `确定认领豆瓣 ID ${row.douban_id}「${row.title}」吗？`,
      '确认认领',
      { confirmButtonText: '认领', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    await adminDoubanIdsApi.acquire(row.douban_id)
    row.is_acquired = 1
    ElMessage.success(`已认领 ${row.douban_id}`)
  } catch (e: any) {
    if (e?.response?.status === 409) {
      row.is_acquired = 1
      ElMessage.warning('已被别人认领')
    } else {
      ElMessage.error(e?.response?.data?.error || '认领失败')
    }
  }
}

async function release(row: DoubanId) {
  try {
    await ElMessageBox.confirm(
      `确定释放豆瓣 ID ${row.douban_id}「${row.title}」吗？`,
      '确认释放',
      { confirmButtonText: '释放', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    await adminDoubanIdsApi.release(row.douban_id)
    row.is_acquired = 0
    ElMessage.success(`已释放 ${row.douban_id}`)
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.warning('释放失败 — 不是你认领的或已被释放')
    } else {
      ElMessage.error(e?.response?.data?.error || '释放失败')
    }
  }
}

onMounted(() => fetchList())
</script>

<style scoped>
.douban-ids-page { max-width: 1080px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.ml-a { margin-left: auto; }
.paginator { margin-top: 16px; justify-content: flex-end; }
</style>
