<template>
  <div class="admin-failures">
    <h2 class="page-title">失败任务</h2>

    <div class="toolbar">
      <el-radio-group v-model="statusFilter" @change="fetchList(1)">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="pending">待处理</el-radio-button>
        <el-radio-button value="claimed">已认领</el-radio-button>
        <el-radio-button value="resolved">已解决</el-radio-button>
      </el-radio-group>
    </div>

    <el-table :data="failures" stripe v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="kind" label="错误类型" width="100">
        <template #default="{ row }">
          <el-tag :type="kindType(row.kind)" size="small">{{ row.kind }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="失败原因" min-width="200" show-overflow-tooltip />
      <el-table-column prop="item_title" label="关联资源" width="150" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <StatusBadge :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column prop="retry_count" label="重试" width="60" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="info" link @click="showDetail(row)">详情</el-button>
          <el-button v-if="row.status === 'pending'" size="small" type="primary" link @click="claim(row)">认领</el-button>
          <el-button v-if="row.status === 'claimed'" size="small" type="warning" link @click="release(row)">释放</el-button>
          <el-button v-if="row.status === 'claimed'" size="small" type="success" link @click="resolve(row)">解决</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="paginator">
      <span class="pager-total">共计 {{ total }} 条</span>
      <el-pagination v-model:current-page="page" :total="total" :page-size="pageSize" background layout="prev, pager, next" @current-change="fetchList" />
    </div>

    <el-dialog v-model="detailVisible" title="失败详情" width="520px">
      <div v-if="detail" class="detail-grid">
        <div class="detail-row"><span class="detail-key">ID</span><span class="detail-value">{{ detail.id }}</span></div>
        <div class="detail-row"><span class="detail-key">错误类型</span><el-tag :type="kindType(detail.kind)" size="small">{{ detail.kind }}</el-tag></div>
        <div class="detail-row"><span class="detail-key">失败原因</span><span class="detail-value detail-mono">{{ detail.reason }}</span></div>
        <div class="detail-row"><span class="detail-key">关联资源</span><span class="detail-value">{{ detail.item_title || '—' }} <span class="c-gray" v-if="detail.item_douban_id">({{ detail.item_douban_id }})</span></span></div>
        <div class="detail-row"><span class="detail-key">范围</span><el-tag size="small" :type="detail.scope === 'item' ? 'warning' : 'info'">{{ detail.scope }}</el-tag></div>
        <div class="detail-row"><span class="detail-key">状态</span><StatusBadge :status="detail.status" /></div>
        <div class="detail-row"><span class="detail-key">重试次数</span><span class="detail-value">{{ detail.retry_count ?? 0 }}</span></div>
        <div class="detail-row"><span class="detail-key">认领人</span><span class="detail-value">{{ detail.claimed_by || '—' }}</span></div>
        <div class="detail-row"><span class="detail-key">认领时间</span><span class="detail-value">{{ detail.claimed_at || '—' }}</span></div>
        <div class="detail-row"><span class="detail-key">解决时间</span><span class="detail-value">{{ detail.resolved_at || '—' }}</span></div>
        <div class="detail-row"><span class="detail-key">创建时间</span><span class="detail-value">{{ detail.created_at }}</span></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { adminFailuresApi } from '@/api/admin/failures'
import type { TaskFailure } from '@/types/failure'

const failures = ref<TaskFailure[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const statusFilter = ref('')
const detail = ref<TaskFailure | null>(null)
const detailVisible = ref(false)

async function fetchList(p = 1) {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: pageSize.value }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await adminFailuresApi.list(params as any)
    failures.value = res.data.items
    total.value = res.data.total ?? 0
    page.value = p
  } catch { /* ignore */ } finally { loading.value = false }
}

async function claim(row: TaskFailure) {
  try {
    await adminFailuresApi.claim(row.id)
    row.status = 'claimed'
    ElMessage.success('已认领')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '认领失败')
  }
}

async function release(row: TaskFailure) {
  try {
    await adminFailuresApi.release(row.id)
    row.status = 'pending'
    ElMessage.info('已释放')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '操作失败')
  }
}

async function resolve(row: TaskFailure) {
  try {
    await adminFailuresApi.resolve(row.id)
    row.status = 'resolved'
    ElMessage.success('已标记为已解决')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '操作失败')
  }
}

function kindType(k: string) {
  const m: Record<string, string> = { network: 'danger', abuse: 'danger', timeout: 'warning', parse: 'info', http: 'info', browser: 'danger', storage: 'warning', unknown: 'info' }
  return m[k] || 'info'
}

async function showDetail(row: TaskFailure) {
  detailVisible.value = true
  detail.value = null
  try {
    const res = await adminFailuresApi.detail(row.id)
    detail.value = res.data
  } catch { /* ignore */ }
}

onMounted(() => fetchList())
</script>

<style scoped>
.admin-failures { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.paginator { margin-top: 16px; display: flex; justify-content: flex-end; align-items: center; }
.pager-total { font-size: 13px; color: #606266; margin-right: 16px; white-space: nowrap; }
.detail-grid { display: flex; flex-direction: column; gap: 10px; }
.detail-row { display: flex; align-items: center; gap: 12px; }
.detail-key { font-size: 13px; color: #909399; min-width: 70px; text-align: right; }
.detail-value { font-size: 14px; color: #303133; word-break: break-all; }
.detail-mono { font-family: monospace; font-size: 13px; }
.c-gray { color: #909399; font-size: 13px; }
</style>
