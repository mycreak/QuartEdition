<template>
  <div class="profile-page">
    <div class="page-header">
      <h2 class="page-title">个人中心</h2>
      <el-button :icon="HomeFilled" @click="router.push('/')">返回首页</el-button>
    </div>

    <el-card class="profile-card" shadow="never">
      <el-form
        ref="formRef"
        :model="form"
        label-width="100px"
        :rules="rules"
        :disabled="loading"
      >
        <!-- 头像区域 -->
        <el-form-item label="头像">
          <AvatarUpload
            v-model="form.avatar_url"
            @success="handleAvatarUploadSuccess"
          />
        </el-form-item>

        <!-- 用户名 -->
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" disabled placeholder="用户名不可修改" />
        </el-form-item>

        <!-- 昵称 -->
        <el-form-item label="昵称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="请输入昵称" maxlength="64" show-word-limit />
        </el-form-item>

        <!-- 权限列表 -->
        <el-form-item label="我的权限" v-if="form.permissions.length">
          <div class="permissions-list">
            <el-tag
              v-for="perm in form.permissions"
              :key="perm"
              size="small"
              type="success"
              effect="light"
            >
              {{ formatPermissionName(perm) }}
            </el-tag>
          </div>
        </el-form-item>

        <!-- 操作按钮 -->
        <el-form-item>
          <el-button type="primary" @click="handleSubmit" :loading="loading">
            保存修改
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { updateProfile } from '@/api/profile'
import { getPermissionShortName } from '@/utils/permission'
import { HomeFilled } from '@element-plus/icons-vue'
import AvatarUpload from '@/components/common/AvatarUpload.vue'

const authStore = useAuthStore()
const router = useRouter()
const formRef = ref<FormInstance | null>(null)
const loading = ref(false)

const form = reactive({
  username: '',
  display_name: '',
  avatar_url: '',
  permissions: [] as string[]
})

const rules: FormRules = {
  display_name: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 1, max: 64, message: '昵称长度在1到64个字符', trigger: 'blur' }
  ]
}

/** 格式化权限名称 — 从集中化 PERMISSION_DESCRIPTIONS 提取短名称 */
const formatPermissionName = getPermissionShortName

/** 初始化表单数据 */
const initForm = () => {
  if (!authStore.user) return
  form.username = authStore.user.username
  form.display_name = authStore.user.display_name
  form.avatar_url = authStore.user.avatar_url || ''
  form.permissions = authStore.user.permissions || []
}

/** 头像上传成功回调 */
const handleAvatarUploadSuccess = (url: string) => {
  form.avatar_url = url
}

/** 提交表单 */
const handleSubmit = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      const params = {
        display_name: form.display_name.trim(),
        avatar_url: form.avatar_url
      }
      const res = await updateProfile(params)
      
      // 更新全局用户信息
      await authStore.updateProfile(res.data.data)
      
      ElMessage.success('保存成功')
    } catch (err: any) {
      ElMessage.error(err.response?.data?.message || '保存失败')
    } finally {
      loading.value = false
    }
  })
}

onMounted(() => {
  initForm()
})
</script>

<style scoped>
.profile-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 30px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 24px;
  color: #1a1a2e;
  margin: 0;
}

.profile-card {
  border-radius: 8px;
  padding: 20px;
}

.permissions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
