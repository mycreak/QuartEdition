<template>
  <div class="infra-page">
    <h2 class="page-title">基础设施管理</h2>

    <el-tabs v-model="activeTab">
      <!-- ═══════ 代理管理 ═══════ -->
      <el-tab-pane label="代理池" name="proxy" v-if="canViewProxy">
        <div class="mb-2 text-sm">
          总数 <strong>{{ proxyStats.total }}</strong> /
          存活 <strong class="c-green">{{ proxyStats.alive }}</strong> /
          死亡 <strong class="c-red">{{ proxyStats.dead }}</strong> /
          封禁 <strong class="c-gray">{{ proxyStats.banned }}</strong>
        </div>
        <div class="toolbar flex-wrap">
          <el-button type="primary" @click="openAddProxy" v-if="canManageProxy">添加代理</el-button>
          <el-button @click="runHealthCheck" :loading="healthChecking" v-if="canManageProxy">全量验证</el-button>
          
          <div class="flex gap-2 ml-auto">
            <el-input
              v-model="proxyFilters.keyword"
              placeholder="搜索主机/备注"
              style="width: 180px"
              clearable
              @clear="fetchProxies(1)"
              @keyup.enter="fetchProxies(1)"
            />
            <el-select
              v-model="proxyFilters.status"
              placeholder="状态筛选"
              style="width: 120px"
              clearable
              @change="fetchProxies(1)"
            >
              <el-option label="全部" value="" />
              <el-option label="启用" value="enabled" />
              <el-option label="禁用" value="disabled" />
              <el-option label="存活" value="alive" />
              <el-option label="死亡" value="dead" />
            </el-select>
            <el-select
              v-model="proxyFilters.region"
              placeholder="地区筛选"
              style="width: 120px"
              clearable
              filterable
              @change="fetchProxies(1)"
            >
              <el-option
                 v-for="region in Array.from(new Set(proxies.map((p: ProxyItem) => p.region).filter(Boolean))).sort()"
                 :key="region"
                 :label="region"
                 :value="region"
               />
            </el-select>
          </div>
        </div>

        <el-table :data="proxies" stripe v-loading="proxyLoading">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="host" label="主机" width="160" />
          <el-table-column prop="port" label="端口" width="70" />

          <el-table-column prop="region" label="地区" width="90" />
          <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column label="认证" width="60">
            <template #default="{ row }">
              <el-tag size="small" type="success" v-if="row.has_auth">有</el-tag>
              <span class="c-gray" v-else>无</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_alive && row.enabled ? 'success' : 'danger'">
                {{ row.enabled ? (row.is_alive ? '存活' : '死亡') : '禁用' }}
              </el-tag>
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
          <el-table-column label="统计" width="100">
            <template #default="{ row }">
              <span class="success-count">✓{{ row.success_count || 0 }}</span>
              <span class="fail-count"> ✗{{ row.fail_count || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最后使用" width="110">
            <template #default="{ row }">
              <span class="c-gray">{{ row.last_used ? formatDate(row.last_used) : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right" v-if="canManageProxy">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="testProxy(row)">验证</el-button>
              <el-button size="small" type="warning" link @click="openEditProxy(row)">编辑</el-button>
              <el-button size="small" type="danger" link @click="confirmRemoveProxy(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          class="mt-4 flex justify-end"
          v-model:current-page="proxyPage"
          :total="proxyTotal"
          :page-size="proxyPageSize"
          background
          layout="total, prev, pager, next"
          @current-change="fetchProxies"
          v-if="proxyTotal > 0"
        />
      </el-tab-pane>

      <!-- ═══════ Cookie管理 ═══════ -->
      <el-tab-pane label="Cookie" name="cookie" v-if="canViewCookie">
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

        <div class="toolbar flex-wrap">
          <el-button type="primary" @click="openAddAccount" v-if="canManageCookie">添加账号</el-button>
          <el-button @click="openReplaceCookie" v-if="canManageCookie">替换 Cookie</el-button>
          <el-button @click="fetchCookieAccounts" :loading="cookieLoading">刷新</el-button>
          
          <div class="flex gap-2 ml-auto">
            <el-input
              v-model="cookieFilters.keyword"
              placeholder="搜索标签/备注"
              style="width: 180px"
              clearable
              @clear="fetchCookieAccounts(1)"
              @keyup.enter="fetchCookieAccounts(1)"
            />
            <el-select
              v-model="cookieFilters.status"
              placeholder="状态筛选"
              style="width: 150px"
              clearable
              @change="fetchCookieAccounts(1)"
            >
              <el-option label="全部" value="" />
              <el-option label="启用" value="enabled" />
              <el-option label="禁用" value="disabled" />
              <el-option label="活跃" value="active" />
              <el-option label="可疑" value="suspicious" />
              <el-option label="封禁" value="banned" />
            </el-select>
          </div>
        </div>

        <el-table :data="cookieAccounts" stripe v-loading="cookieLoading" empty-text="暂无 Cookie 账号">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="label" label="标签" width="120">
            <template #default="{ row }">
              <span :class="{ 'no-label': !row.label }">{{ row.label || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="platform" label="平台" width="80">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ row.platform || 'douban' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? stateType(row.state) : 'info'">
                {{ row.enabled ? stateLabel(row.state) : '禁用' }}
              </el-tag>
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
          <el-table-column label="绑定管理员" width="130">
            <template #default="{ row }">
              <template v-if="row.bound_admin_ids?.length">
                <el-tag v-for="id in row.bound_admin_ids" :key="id" size="small" type="warning" class="region-tag">
                  {{ getAdminName(id) }}
                </el-tag>
              </template>
              <span v-else class="c-gray">所有人</span>
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
              <span class="c-gray"> / 总{{ row.usage_count || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最后使用" width="110">
            <template #default="{ row }">
              <span class="c-gray">{{ row.last_used_at ? formatDate(row.last_used_at) : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="保存时间" width="110">
            <template #default="{ row }">
              <span class="c-gray">{{ formatDate(row.saved_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right" v-if="canManageCookie">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="testCookie(row)">验证</el-button>
              <el-button size="small" type="warning" link @click="openEditCookie(row)">编辑</el-button>
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

        <el-pagination
          class="mt-4 flex justify-end"
          v-model:current-page="cookiePage"
          :total="cookieTotal"
          :page-size="cookiePageSize"
          background
          layout="total, prev, pager, next"
          @current-change="fetchCookieAccounts"
          v-if="cookieTotal > 0"
        />
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
        <el-form-item label="备注">
          <el-input v-model="proxyAddForm.remark" placeholder="选填，如 香港住宅代理" />
        </el-form-item>
        <el-form-item label="认证信息（选填）">
          <el-input v-model="proxyAddForm.username" placeholder="用户名" style="margin-bottom: 8px" />
          <el-input v-model="proxyAddForm.password" placeholder="密码" type="password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="proxyAddVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddProxy" :loading="proxyAdding">添加</el-button>
      </template>
    </el-dialog>

    <!-- 编辑Cookie弹窗 -->
    <el-dialog v-model="cookieEditVisible" title="编辑Cookie" width="480px">
      <el-form :model="cookieEditForm" label-position="top">
        <el-form-item label="标签">
          <el-input v-model="cookieEditForm.label" placeholder="选填，给Cookie起个容易识别的名称" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="cookieEditForm.remark" type="textarea" :rows="2" placeholder="选填，添加备注信息" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="cookieEditForm.platform" style="width: 100%">
            <el-option label="豆瓣" value="douban" />
          </el-select>
        </el-form-item>
        <el-form-item label="允许地区">
          <el-select
            v-model="cookieEditForm.allowed_regions"
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
          <div class="form-hint">该Cookie仅允许用于这些地区的代理</div>
        </el-form-item>
        <el-form-item label="绑定管理员">
          <el-select
            v-model="cookieEditForm.bound_admin_ids"
            multiple
            filterable
            placeholder="选择允许使用此Cookie的管理员（空=所有管理员可用）"
            style="width: 100%"
          >
            <el-option
              v-for="admin in adminList"
              :key="admin.id"
              :label="`${admin.display_name} (${admin.username})`"
              :value="admin.id"
            />
          </el-select>
          <div class="form-hint">空 = 所有管理员均可使用；选中后仅指定管理员可用</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="cookieEditForm.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cookieEditVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditCookie" :loading="cookieEditing">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑代理弹窗 -->
    <el-dialog v-model="proxyEditVisible" title="编辑代理" width="420px">
      <el-form :model="proxyEditForm" label-position="top">
        <el-form-item label="备注">
          <el-input v-model="proxyEditForm.remark" placeholder="选填，如 香港住宅代理" />
        </el-form-item>
        <el-form-item label="地区">
          <el-input v-model="proxyEditForm.region" placeholder="选填，如 香港" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="proxyEditForm.username" placeholder="选填，代理认证用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="proxyEditForm.password" type="password" placeholder="选填，代理认证密码" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="proxyEditForm.enabled" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="proxyEditVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditProxy" :loading="proxyEditing">保存</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 添加 Cookie 账号弹窗 ═══════ -->
    <el-dialog v-model="accountAddVisible" title="添加 Cookie 账号" width="520px">
      <el-form :model="accountAddForm" label-position="top">
        <el-form-item label="平台">
          <el-select v-model="accountAddForm.platform" style="width: 100%">
            <el-option label="豆瓣" value="douban" />
          </el-select>
        </el-form-item>
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
        <el-form-item label="备注（选填）">
          <el-input v-model="accountAddForm.remark" type="textarea" :rows="2" placeholder="添加备注信息" />
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
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminProxyApi, adminCookieApi, type ProxyItem, type CookieAccount, type CookieStats } from '@/api/admin/infra'
import { adminUsersApi } from '@/api/admin/users'
import { useAuthStore } from '@/stores/auth'
import { formatDate } from '@/utils/format'

const authStore = useAuthStore()
const adminList = ref<{ id: number; username: string; display_name: string }[]>([])

async function fetchAdminList() {
  try {
    const res = await adminUsersApi.list()
    adminList.value = res.data.items || []
  } catch { /* ignore */ }
}

function getAdminName(id: number): string {
  const admin = adminList.value.find(a => a.id === id)
  return admin ? admin.username : `#${id}`
}
// 权限判断（system:monitor → infra:* 兼容逻辑已内置于 hasPermission()）
const canViewProxy = computed(() => authStore.checkPermission('infra:proxy:read'))
const canManageProxy = computed(() => authStore.checkPermission('infra:proxy:manage'))
const canViewCookie = computed(() => authStore.checkPermission('infra:cookie:read'))
const canManageCookie = computed(() => authStore.checkPermission('infra:cookie:manage'))
const canViewSensitive = computed(() => authStore.checkPermission('infra:sensitive:read'))

const activeTab = ref('proxy')

/* ── 代理 ── */
const proxies = ref<ProxyItem[]>([])
const proxyStats = reactive<ProxyStats>({ total: 0, alive: 0, dead: 0, banned: 0 })
const proxyLoading = ref(false)
const healthChecking = ref(false)
const proxyAddVisible = ref(false)
const proxyAdding = ref(false)
const proxyAddForm = reactive({ host: '', port: '8080', region: '', remark: '', username: '', password: '' })
const proxyEditVisible = ref(false)
const proxyEditing = ref(false)
const proxyEditForm = reactive({ id: 0, remark: '', username: '', password: '', region: '', enabled: true })
const proxyFilters = reactive({ status: '', region: '', keyword: '' })
const proxyPage = ref(1)
const proxyPageSize = ref(10)
const proxyTotal = ref(0)

interface ProxyStats {
  total: number; alive: number; dead: number; banned: number
}

async function fetchProxies(page = 1) {
  proxyLoading.value = true
  try {
    const res = await adminProxyApi.list({
      ...proxyFilters,
      page,
      page_size: proxyPageSize.value,
    })
    proxies.value = res.data.items || []
    proxyTotal.value = res.data.total
    proxyPage.value = res.data.page
    Object.assign(proxyStats, res.data.stats || {})
  } catch { /* ignore */ } finally { proxyLoading.value = false }
}

function openAddProxy() {
  proxyAddForm.host = ''
  proxyAddForm.port = '8080'
  proxyAddForm.region = ''
  proxyAddForm.remark = ''
  proxyAddForm.username = ''
  proxyAddForm.password = ''
  proxyAddVisible.value = true
}

// 打开编辑代理弹窗
function openEditProxy(row: ProxyItem) {
  proxyEditForm.id = row.id
  proxyEditForm.remark = row.remark || ''
  proxyEditForm.region = row.region || ''
  proxyEditForm.username = '' // 出于安全考虑，密码不回填
  proxyEditForm.password = ''
  proxyEditForm.enabled = row.enabled
  proxyEditVisible.value = true
}

// 提交编辑代理
async function submitEditProxy() {
  proxyEditing.value = true
  try {
    const updateData: any = {}
    if (proxyEditForm.remark) updateData.remark = proxyEditForm.remark
    if (proxyEditForm.region) updateData.region = proxyEditForm.region
    if (proxyEditForm.username) updateData.username = proxyEditForm.username
    if (proxyEditForm.password) updateData.password = proxyEditForm.password
    updateData.enabled = proxyEditForm.enabled

    await adminProxyApi.update(proxyEditForm.id, updateData)
    ElMessage.success('代理信息已更新')
    proxyEditVisible.value = false
    await fetchProxies()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '更新失败')
  } finally { proxyEditing.value = false }
}

async function testProxy(row: ProxyItem) {
  try {
    const res = await adminProxyApi.test({ host: row.host, port: row.port })
    if (res.data.success) {
      ElMessage.success(`验证成功，延迟 ${res.data.latency_ms}ms，出口IP ${res.data.exit_ip}`)
    } else {
      ElMessage.error(`验证失败: ${res.data.message}`)
    }
    await fetchProxies()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '验证失败')
  }
}



async function submitAddProxy() {
  proxyAdding.value = true
  try {
    await adminProxyApi.add({
      host: proxyAddForm.host,
      port: Number(proxyAddForm.port),
      region: proxyAddForm.region || '',
      remark: proxyAddForm.remark || '',
      proxy_type: 'https',
      username: proxyAddForm.username || undefined,
      password: proxyAddForm.password || undefined,
    })
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
    await adminProxyApi.remove(row.id)
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
const cookieFilters = reactive({ status: '', keyword: '' })
const cookiePage = ref(1)
const cookiePageSize = ref(10)
const cookieTotal = ref(0)

const accountAddVisible = ref(false)
const accountAdding = ref(false)
const accountAddForm = reactive({
  platform: 'douban', 
  dbcl2: '', 
  allowed_regions: [] as string[], 
  bid: '', 
  label: '', 
  remark: '',
})

const cookieReplaceVisible = ref(false)
const cookieReplaceForm = reactive({ dbcl2: '', bid: '' })

const cookieEditVisible = ref(false)
const cookieEditing = ref(false)
const cookieEditForm = reactive({
  id: '',
  label: '',
  remark: '',
  platform: 'douban',
  enabled: true,
  allowed_regions: [] as string[],
  bound_admin_ids: [] as number[],
})

function stateType(state: string): string {
  const m: Record<string, string> = { active: 'success', suspicious: 'warning', banned: 'danger' }
  return m[state] || 'info'
}

function stateLabel(state: string): string {
  const m: Record<string, string> = { active: '活跃', suspicious: '可疑', banned: '封禁' }
  return m[state] || state
}

async function fetchCookieAccounts(page = 1) {
  cookieLoading.value = true
  try {
    const res = await adminCookieApi.list({
      ...cookieFilters,
      page,
      page_size: cookiePageSize.value,
    })
    cookieAccounts.value = res.data.items || []
    cookieTotal.value = res.data.total
    cookiePage.value = res.data.page
    Object.assign(cookieStats, res.data.stats || {})

    const statusRes = await adminCookieApi.status()
    cookieSummary.value = {
      has_dbcl2: statusRes.data.has_dbcl2,
      cookie_valid: statusRes.data.cookie_valid,
    }
  } catch { /* ignore */ } finally { cookieLoading.value = false }
}

function openAddAccount() {
  accountAddForm.platform = 'douban'
  accountAddForm.dbcl2 = ''
  accountAddForm.allowed_regions = []
  accountAddForm.bid = ''
  accountAddForm.label = ''
  accountAddForm.remark = ''
  accountAddVisible.value = true
}

async function testCookie(row: CookieAccount) {
  try {
    const res = await adminCookieApi.test({ id: row.id })
    if (res.data.success) {
      ElMessage.success('Cookie验证成功，当前有效')
    } else {
      ElMessage.error(`验证失败: ${res.data.message}`)
    }
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '验证失败')
  }
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
      platform: accountAddForm.platform,
      dbcl2: accountAddForm.dbcl2,
      allowed_regions: accountAddForm.allowed_regions,
      bid: accountAddForm.bid || undefined,
      label: accountAddForm.label || undefined,
      remark: accountAddForm.remark || undefined,
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

// 打开编辑Cookie弹窗
function openEditCookie(row: CookieAccount) {
  cookieEditForm.id = row.id
  cookieEditForm.label = row.label || ''
  cookieEditForm.remark = row.remark || ''
  cookieEditForm.platform = row.platform
  cookieEditForm.enabled = row.enabled
  cookieEditForm.allowed_regions = [...row.allowed_regions]
  cookieEditForm.bound_admin_ids = [...(row.bound_admin_ids || [])]
  cookieEditVisible.value = true
}

// 提交编辑Cookie
async function submitEditCookie() {
  cookieEditing.value = true
  try {
    const updateData: any = {}
    if (cookieEditForm.label) updateData.label = cookieEditForm.label
    if (cookieEditForm.remark) updateData.remark = cookieEditForm.remark
    updateData.platform = cookieEditForm.platform
    updateData.enabled = cookieEditForm.enabled
    updateData.allowed_regions = cookieEditForm.allowed_regions
    updateData.bound_admin_ids = cookieEditForm.bound_admin_ids

    await adminCookieApi.update(cookieEditForm.id, updateData)
    ElMessage.success('Cookie信息已更新')
    cookieEditVisible.value = false
    await fetchCookieAccounts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '更新失败')
  } finally { cookieEditing.value = false }
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



onMounted(() => { fetchProxies(); fetchCookieAccounts(); fetchAdminList() })
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
