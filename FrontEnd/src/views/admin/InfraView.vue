<template>
  <div class="infra-page">
    <h2 class="page-title">基础设施管理</h2>

    <el-tabs v-model="activeTab">
      <!-- ═══════ 代理管理 ═══════ -->
      <el-tab-pane label="代理池" name="proxy">
        <div class="toolbar">
          <el-button type="primary" @click="openAddProxy">添加代理</el-button>
          <el-button @click="runHealthCheck" :loading="healthChecking">全量验证</el-button>
          <span class="stat-summary">
            总数 <strong>{{ proxyStats.total }}</strong> /
            存活 <strong class="c-green">{{ proxyStats.alive }}</strong> /
            死亡 <strong class="c-red">{{ proxyStats.dead }}</strong> /
            封禁 <strong class="c-gray">{{ proxyStats.banned }}</strong>
          </span>
        </div>

        <el-table :data="proxies" stripe v-loading="proxyLoading">
          <el-table-column prop="host" label="主机" width="160" />
          <el-table-column prop="port" label="端口" width="70" />
          <el-table-column prop="region" label="地区" width="90" />
          <el-table-column prop="source" label="来源" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.source === 'admin' ? 'warning' : 'info'">{{ row.source }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_alive ? 'success' : 'danger'">{{ row.is_alive ? '存活' : '死亡' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="成功率" width="80">
            <template #default="{ row }">
              {{ row.success_rate != null ? row.success_rate + '%' : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="延迟" width="80">
            <template #default="{ row }">
              {{ row.avg_latency_ms != null ? row.avg_latency_ms + 'ms' : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="confirmRemoveProxy(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ═══════ Cookie 管理（多账号） ═══════ -->
      <el-tab-pane label="Cookie" name="cookie">
        <div class="cookie-stats-bar">
          <div class="stat-item">
            <span class="stat-number">{{ cookieStats.total }}</span>
            <span class="stat-label">总数</span>
          </div>
          <div class="stat-item">
            <span class="stat-number c-green">{{ cookieStats.active }}</span>
            <span class="stat-label">活跃</span>
          </div>
          <div class="stat-item">
            <span class="stat-number c-orange">{{ cookieStats.suspicious }}</span>
            <span class="stat-label">可疑</span>
          </div>
          <div class="stat-item">
            <span class="stat-number c-red">{{ cookieStats.banned }}</span>
            <span class="stat-label">封禁</span>
          </div>
          <div class="stat-item" v-for="(count, region) in cookieStats.by_region" :key="region">
            <span class="stat-number c-blue">{{ count }}</span>
            <span class="stat-label">{{ region }}</span>
          </div>
        </div>

        <div class="cookie-status-summary" v-if="cookieSummary">
          <el-tag :type="cookieSummary.has_dbcl2 ? 'success' : 'danger'" size="small">
            {{ cookieSummary.has_dbcl2 ? '有 dbcl2 Cookie' : '无 dbcl2 Cookie' }}
          </el-tag>
          <el-tag v-if="cookieSummary.cookie_valid" type="success" size="small">整体可用</el-tag>
        </div>

        <div class="toolbar">
          <el-button type="primary" @click="openAddAccount">添加账号</el-button>
          <el-button @click="openReplaceCookie">替换 Cookie</el-button>
          <el-button @click="fetchCookieAccounts" :loading="cookieLoading">刷新</el-button>
        </div>

        <el-table :data="cookieAccounts" stripe v-loading="cookieLoading" empty-text="暂无 Cookie 账号">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="label" label="标签" width="120">
            <template #default="{ row }">
              <span :class="{ 'no-label': !row.label }">{{ row.label || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="stateType(row.state)">{{ stateLabel(row.state) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="dbcl2" width="120">
            <template #default="{ row }">
              <code class="dbcl2-preview">{{ row.dbcl2_preview || '—' }}</code>
            </template>
          </el-table-column>
          <el-table-column label="允许地区" width="160">
            <template #default="{ row }">
              <el-tag v-for="r in row.allowed_regions" :key="r" size="small" class="region-tag">{{ r }}</el-tag>
              <span v-if="!row.allowed_regions?.length" class="c-gray">不限</span>
            </template>
          </el-table-column>
          <el-table-column label="使用统计" width="160">
            <template #default="{ row }">
              <el-tooltip content="该 Cookie 累计成功使用的次数。每次成功请求后 +1，同时连续失败计数归零。" placement="top">
                <span class="success-count">✓{{ row.success_count }}</span>
              </el-tooltip>
              <el-tooltip v-if="row.fail_count > 0" content="该 Cookie 连续失败的次数。fail_count≥1 时状态变为可疑(suspicious)，达到阈值后自动封禁(banned)。" placement="top">
                <span class="fail-count"> ✗{{ row.fail_count }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="保存时间" width="110">
            <template #default="{ row }">
              <span class="c-gray">{{ formatDate(row.saved_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.state === 'banned'"
                size="small" type="success" link
                @click="unbanAccount(row)"
              >恢复</el-button>
              <el-button
                v-else size="small" type="warning" link
                @click="banAccount(row)"
              >封禁</el-button>
              <el-button
                size="small" type="danger" link
                @click="confirmRemoveAccount(row)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══════ 添加代理弹窗 ═══════ -->
    <el-dialog v-model="proxyAddVisible" title="添加代理" width="420px">
      <el-form :model="proxyAddForm" label-position="top">
        <el-form-item label="主机地址">
          <el-input v-model="proxyAddForm.host" placeholder="如 1.2.3.4" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input v-model="proxyAddForm.port" placeholder="如 8080" />
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="proxyAddForm.region" placeholder="选填，如 香港" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="proxyAddVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddProxy" :loading="proxyAdding">添加</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 添加 Cookie 账号弹窗 ═══════ -->
    <el-dialog v-model="accountAddVisible" title="添加 Cookie 账号" width="520px">
      <el-form :model="accountAddForm" label-position="top">
        <el-form-item label="dbcl2（必填）">
          <el-input
            v-model="accountAddForm.dbcl2" type="textarea" :rows="3"
            placeholder="从浏览器 DevTools → Application → Cookies → .douban.com → dbcl2 复制"
          />
        </el-form-item>
        <el-form-item label="允许的地区">
          <el-select
            v-model="accountAddForm.allowed_regions"
            multiple
            allow-create
            default-first-option
            placeholder="输入地区代码，如 CN"
            style="width: 100%"
          >
            <el-option label="中国 (CN)" value="CN" />
            <el-option label="香港 (HK)" value="HK" />
            <el-option label="台湾 (TW)" value="TW" />
            <el-option label="日本 (JP)" value="JP" />
            <el-option label="美国 (US)" value="US" />
            <el-option label="韩国 (KR)" value="KR" />
          </el-select>
          <div class="form-hint">该账号的 Cookie 仅允许用于这些地区的代理</div>
        </el-form-item>
        <el-form-item label="bid（选填）">
          <el-input v-model="accountAddForm.bid" placeholder="同上，复制 bid 值" />
        </el-form-item>
        <el-form-item label="标签（选填）">
          <el-input v-model="accountAddForm.label" placeholder="如 主账号、备用1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountAddVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddAccount" :loading="accountAdding">添加</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 替换 Cookie 弹窗 ═══════ -->
    <el-dialog v-model="cookieReplaceVisible" title="替换 Cookie" width="520px">
      <p class="dialog-desc">替换默认账号 (<code>main</code>) 的 Cookie，等价于添加/覆盖 ID 为 <code>main</code> 的账号。</p>
      <el-form :model="cookieReplaceForm" label-position="top">
        <el-form-item label="dbcl2（必填）">
          <el-input
            v-model="cookieReplaceForm.dbcl2" type="textarea" :rows="3"
            placeholder="从浏览器 DevTools → Application → Cookies → .douban.com → dbcl2 复制"
          />
        </el-form-item>
        <el-form-item label="bid（选填）">
          <el-input v-model="cookieReplaceForm.bid" placeholder="同上，复制 bid 值" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cookieReplaceVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReplaceCookie" :loading="cookieSaving">确认替换</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminProxyApi, adminCookieApi, type ProxyItem, type CookieAccount, type CookieStats } from '@/api/admin/infra'
import { formatDate } from '@/utils/format'

const activeTab = ref('proxy')

/* ── 代理 ── */
const proxies = ref<ProxyItem[]>([])
const proxyStats = reactive<ProxyStats>({ total: 0, alive: 0, dead: 0, banned: 0 })
const proxyLoading = ref(false)
const healthChecking = ref(false)
const proxyAddVisible = ref(false)
const proxyAdding = ref(false)
const proxyAddForm = reactive({ host: '', port: '8080', region: '' })

interface ProxyStats {
  total: number; alive: number; dead: number; banned: number
}

async function fetchProxies() {
  proxyLoading.value = true
  try {
    const res = await adminProxyApi.list()
    proxies.value = res.data.proxies || []
    Object.assign(proxyStats, res.data.stats || {})
  } catch { /* ignore */ } finally { proxyLoading.value = false }
}

function openAddProxy() {
  proxyAddForm.host = ''
  proxyAddForm.port = '8080'
  proxyAddForm.region = ''
  proxyAddVisible.value = true
}

async function submitAddProxy() {
  proxyAdding.value = true
  try {
    await adminProxyApi.add({ host: proxyAddForm.host, port: Number(proxyAddForm.port), region: proxyAddForm.region || '' })
    ElMessage.success(`代理 ${proxyAddForm.host}:${proxyAddForm.port} 已添加`)
    proxyAddVisible.value = false
    await fetchProxies()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '添加失败')
  } finally { proxyAdding.value = false }
}

async function confirmRemoveProxy(row: ProxyItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除代理 ${row.host}:${row.port} 吗？`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    await adminProxyApi.remove(row.host, row.port)
    ElMessage.success(`代理 ${row.host}:${row.port} 已删除`)
    await fetchProxies()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '删除失败')
  }
}

async function runHealthCheck() {
  healthChecking.value = true
  try {
    const res = await adminProxyApi.healthCheck()
    ElMessage.success(`全量验证完成: ${JSON.stringify(res.data)}`)
    await fetchProxies()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '验证失败')
  } finally { healthChecking.value = false }
}

/* ── Cookie 多账号 ── */
const cookieAccounts = ref<CookieAccount[]>([])
const cookieStats = reactive<CookieStats>({ total: 0, active: 0, suspicious: 0, banned: 0, by_region: {} })
const cookieSummary = ref<{ has_dbcl2: boolean; cookie_valid: boolean } | null>(null)
const cookieLoading = ref(false)
const cookieSaving = ref(false)

const accountAddVisible = ref(false)
const accountAdding = ref(false)
const accountAddForm = reactive({
  dbcl2: '', allowed_regions: [] as string[], bid: '', label: '',
})

const cookieReplaceVisible = ref(false)
const cookieReplaceForm = reactive({ dbcl2: '', bid: '' })

function stateType(state: string): string {
  const m: Record<string, string> = { active: 'success', suspicious: 'warning', banned: 'danger' }
  return m[state] || 'info'
}

function stateLabel(state: string): string {
  const m: Record<string, string> = { active: '活跃', suspicious: '可疑', banned: '封禁' }
  return m[state] || state
}

async function fetchCookieAccounts() {
  cookieLoading.value = true
  try {
    const res = await adminCookieApi.list()
    cookieAccounts.value = res.data.items || []
    Object.assign(cookieStats, res.data.stats || {})

    const statusRes = await adminCookieApi.status()
    cookieSummary.value = {
      has_dbcl2: statusRes.data.has_dbcl2,
      cookie_valid: statusRes.data.cookie_valid,
    }
  } catch { /* ignore */ } finally { cookieLoading.value = false }
}

function openAddAccount() {
  accountAddForm.dbcl2 = ''
  accountAddForm.allowed_regions = ['CN']
  accountAddForm.bid = ''
  accountAddForm.label = ''
  accountAddVisible.value = true
}

async function submitAddAccount() {
  if (!accountAddForm.dbcl2.trim()) {
    ElMessage.warning('dbcl2 不能为空')
    return
  }
  if (!accountAddForm.allowed_regions.length) {
    ElMessage.warning('请选择至少一个允许的地区')
    return
  }
  accountAdding.value = true
  try {
    const res = await adminCookieApi.add({
      dbcl2: accountAddForm.dbcl2,
      allowed_regions: accountAddForm.allowed_regions,
      bid: accountAddForm.bid || undefined,
      label: accountAddForm.label || undefined,
    })
    ElMessage.success(`账号 ${res.data.account_id} 已添加`)
    accountAddVisible.value = false
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '添加失败')
  } finally { accountAdding.value = false }
}

async function banAccount(row: CookieAccount) {
  try {
    await ElMessageBox.confirm(
      `确定封禁账号 <strong>${row.id}</strong>（${row.label || row.id}）吗？封禁后爬虫将不再使用此账号。`,
      '确认封禁',
      { confirmButtonText: '封禁', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true }
    )
  } catch { return }
  try {
    await adminCookieApi.ban(row.id)
    ElMessage.success(`账号 ${row.id} 已封禁`)
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '操作失败')
  }
}

async function unbanAccount(row: CookieAccount) {
  try {
    await ElMessageBox.confirm(
      `确定恢复账号 <strong>${row.id}</strong>（${row.label || row.id}）吗？恢复后爬虫可正常使用此账号。`,
      '确认恢复',
      { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true }
    )
  } catch { return }
  try {
    await adminCookieApi.unban(row.id)
    ElMessage.success(`账号 ${row.id} 已恢复`)
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '操作失败')
  }
}

async function confirmRemoveAccount(row: CookieAccount) {
  try {
    await ElMessageBox.confirm(
      `确定删除账号 <strong>${row.id}</strong>（${row.label || row.id}）吗？同时会清理对应的 Cookie 文件。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true }
    )
  } catch { return }
  try {
    await adminCookieApi.remove(row.id)
    ElMessage.success(`账号 ${row.id} 已删除`)
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '删除失败')
  }
}

function openReplaceCookie() {
  cookieReplaceForm.dbcl2 = ''
  cookieReplaceForm.bid = ''
  cookieReplaceVisible.value = true
}

async function submitReplaceCookie() {
  cookieSaving.value = true
  try {
    const res = await adminCookieApi.replace({
      dbcl2: cookieReplaceForm.dbcl2,
      bid: cookieReplaceForm.bid || undefined,
    })
    ElMessage.success(`Cookie 已替换，账号 ${res.data.account_id}`)
    cookieReplaceVisible.value = false
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '替换失败')
  } finally { cookieSaving.value = false }
}

onMounted(() => { fetchProxies(); fetchCookieAccounts() })
</script>

<style scoped>
.infra-page { max-width: 1140px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }

/* ── 通用 ── */
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }

.stat-summary { margin-left: auto; font-size: 13px; color: #606266; white-space: nowrap; }
.stat-summary strong { margin: 0 2px; }

.c-green { color: #67c23a; }
.c-red { color: #f56c6c; }
.c-orange { color: #e6a23c; }
.c-blue { color: #409eff; }
.c-gray { color: #909399; }
.no-label { color: #c0c4cc; }

/* ── Cookie 统计栏 ── */
.cookie-stats-bar {
  display: flex;
  gap: 20px;
  margin-bottom: 12px;
  padding: 14px 20px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-number {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.cookie-status-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.region-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.dbcl2-preview {
  font-size: 12px;
  color: #606266;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
}

.success-count { color: #67c23a; font-weight: 600; }
.fail-count { color: #f56c6c; font-weight: 600; }

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.dialog-desc {
  font-size: 13px;
  color: #606266;
  margin: 0 0 16px;
  line-height: 1.6;
}

.dialog-desc code {
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
}
</style>
