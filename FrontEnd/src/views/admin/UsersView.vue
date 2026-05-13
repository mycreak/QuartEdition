<template>
  <div class="users-page">
    <h2 class="page-title">用户管理</h2>

    <el-button type="primary" @click="openCreate" class="create-btn">创建用户</el-button>

    <el-table :data="pagedUsers" stripe v-loading="loading">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="150" />
      <el-table-column prop="display_name" label="显示名" width="150" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '活跃' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="80">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" size="small">{{ row.role === 'admin' ? '管理员' : '用户' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="权限" min-width="200">
        <template #default="{ row }">
          <el-tag v-for="p in (row.permissions || [])" :key="p" size="small" class="perm-tag">{{ p }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEditPermissions(row)">权限</el-button>
          <el-button size="small" type="primary" link @click="openRename(row)">改名</el-button>
          <el-button v-if="row.is_active" size="small" type="danger" link @click="confirmDisable(row)">禁用</el-button>
          <el-button v-else size="small" type="success" link @click="confirmEnable(row)">恢复</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="paginator-row">
      <span class="pager-total">共计 {{ total }} 条</span>
      <el-pagination
        v-model:current-page="page"
        :total="total"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        background
        layout="sizes, prev, pager, next"
        @size-change="pageSize = $event; page = 1"
      />
    </div>

    <el-dialog v-model="createVisible" title="创建用户" width="450px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="6-32 位字母数字下划线" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="6-128 位，需包含大写+小写+数字" />
        </el-form-item>
        <el-form-item label="显示名" prop="display_name">
          <el-input v-model="createForm.display_name" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCreate" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="permVisible" title="分配权限" width="500px">
      <template v-if="permUser">
        <p class="perm-hint">用户: <strong>{{ permUser.username }}</strong></p>
        <el-checkbox-group v-model="permSelected" class="perm-group">
          <el-checkbox v-for="code in allPerms" :key="code" :label="code" :value="code">{{ code }}</el-checkbox>
        </el-checkbox-group>
      </template>
      <template #footer>
        <el-button @click="permVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmPermissions" :loading="savingPerms">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="renameVisible" title="修改显示名" width="400px">
      <p style="margin:0 0 16px;color:#606266">用户: <strong>{{ renameUser?.username }}</strong></p>
      <el-form @submit.prevent="confirmRename">
        <el-form-item label="显示名">
          <el-input v-model="renameDisplayName" placeholder="新昵称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmRename" :loading="renaming">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { PERMISSION_CODES, PERMISSION_DESCRIPTIONS } from '@/utils/permission'
import { validateUsername, validatePassword } from '@/utils/validation'
import { adminUsersApi, type AdminUser } from '@/api/admin/users'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const allPerms = [...PERMISSION_CODES]

const users = ref<AdminUser[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)

const total = computed(() => users.value.length)

const pagedUsers = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return users.value.slice(start, start + pageSize.value)
})
const createVisible = ref(false)
const creating = ref(false)
const permVisible = ref(false)
const permUser = ref<AdminUser | null>(null)
const permSelected = ref<string[]>([])
const savingPerms = ref(false)
const renameVisible = ref(false)
const renameUser = ref<AdminUser | null>(null)
const renameDisplayName = ref('')
const renaming = ref(false)

const createForm = reactive({ username: '', password: '', display_name: '' })
const createFormRef = ref<FormInstance>()

const createRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { validator: validateUsername, trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { validator: validatePassword, trigger: 'blur' },
  ],
}

async function fetchUsers() {
  loading.value = true
  try {
    const res = await adminUsersApi.list()
    users.value = res.data.items
  } catch { /* ignore */ } finally { loading.value = false }
}

function openCreate() {
  createForm.username = ''
  createForm.password = ''
  createForm.display_name = ''
  createVisible.value = true
}

async function confirmCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return

  creating.value = true
  try {
    await adminUsersApi.create({ username: createForm.username, password: createForm.password, display_name: createForm.display_name || undefined })
    ElMessage.success(`用户 ${createForm.username} 已创建`)
    createVisible.value = false
    await fetchUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '创建失败')
  } finally { creating.value = false }
}

function openEditPermissions(user: AdminUser) {
  permUser.value = user
  permSelected.value = [...(user.permissions || [])]
  permVisible.value = true
}

async function confirmPermissions() {
  if (!permUser.value) return

  const username = permUser.value.username
  const selected = permSelected.value
  let htmlMessage: string

  if (selected.length === 0) {
    htmlMessage = `<p style="margin:0 0 12px">即将把 <strong style="color:#e6a23c;font-size:15px">${username}</strong> 设置成<strong style="color:#e6a23c">普通用户</strong></p>`
    htmlMessage += `<p style="margin:0;color:#909399;font-size:13px">该用户将不再拥有任何管理权限</p>`
  } else {
    htmlMessage = `<p style="margin:0 0 12px">操作用户：<strong style="color:#409eff;font-size:15px">${username}</strong></p>`
    htmlMessage += `<p style="margin:0 0 8px;color:#606266">取得权限：</p>`
    htmlMessage += `<ul style="margin:0;padding-left:20px">`
    for (const code of selected) {
      const desc = PERMISSION_DESCRIPTIONS[code as keyof typeof PERMISSION_DESCRIPTIONS] || code
      htmlMessage += `<li style="margin:6px 0;line-height:1.5"><code style="background:#f5f7fa;padding:0 6px;border-radius:3px;color:#606266">${code}</code> — <span style="color:#606266">${desc}</span></li>`
    }
    htmlMessage += `</ul>`
  }

  try {
    await ElMessageBox.confirm(htmlMessage, '确认权限变更', {
      confirmButtonText: selected.length === 0 ? '确认降级' : '确认分配',
      cancelButtonText: '取消',
      type: 'warning',
      dangerouslyUseHTMLString: true,
    })
  } catch { return }

  savingPerms.value = true
  try {
    const res = await adminUsersApi.assignPermissions(permUser.value.id, permSelected.value)
    ElMessage.success(`权限已更新 (${res.data.granted}/${res.data.total})`)
    permVisible.value = false
    await fetchUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '保存失败')
  } finally { savingPerms.value = false }
}

function openRename(user: AdminUser) {
  renameUser.value = user
  renameDisplayName.value = user.display_name || ''
  renameVisible.value = true
}

async function confirmRename() {
  if (!renameUser.value || !renameDisplayName.value.trim()) return
  renaming.value = true
  try {
    const res = await adminUsersApi.update(renameUser.value.id, { display_name: renameDisplayName.value.trim() })
    ElMessage.success(`显示名已更新为「${res.data.display_name}」`)
    renameVisible.value = false
    await fetchUsers()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '修改失败')
  } finally { renaming.value = false }
}

async function confirmDisable(user: AdminUser) {
  if (user.username === authStore.user?.username) {
    ElMessage.warning('不能禁用自己')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要禁用用户 <strong>${user.username}</strong> 吗？该用户将无法登录。`,
      '确认禁用',
      { confirmButtonText: '禁用', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true }
    )
  } catch { return }
  try {
    await adminUsersApi.update(user.id, { is_active: false })
    user.is_active = false
    ElMessage.success(`用户 ${user.username} 已禁用`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '操作失败')
  }
}

async function confirmEnable(user: AdminUser) {
  try {
    await ElMessageBox.confirm(
      `确定恢复用户 <strong>${user.username}</strong> 的登录权限吗？`,
      '确认恢复',
      { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning', dangerouslyUseHTMLString: true }
    )
  } catch { return }
  try {
    await adminUsersApi.update(user.id, { is_active: true })
    user.is_active = true
    ElMessage.success(`用户 ${user.username} 已恢复`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '操作失败')
  }
}

onMounted(() => fetchUsers())
</script>

<style scoped>
.users-page { max-width: 1000px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.create-btn { margin-bottom: 16px; }
.perm-tag { margin-right: 4px; margin-bottom: 2px; }
.perm-hint { margin-bottom: 16px; }
.perm-group { display: flex; flex-direction: column; gap: 8px; }
.paginator-row { display: flex; justify-content: flex-end; align-items: center; margin-top: 12px; margin-bottom: 4px; }
.pager-total { font-size: 13px; color: #606266; margin-right: 16px; }
</style>
