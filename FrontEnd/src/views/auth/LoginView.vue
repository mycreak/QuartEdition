<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <h1 class="login-title">QuartEdition</h1>
        <p class="login-subtitle">豆瓣电影数据采集与管理平台</p>
      </div>

      <el-alert
        v-if="authError"
        :title="authError"
        type="error"
        :closable="true"
        show-icon
        @close="authError = ''"
        class="login-alert"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :disabled="loading"
            autocomplete="username"
            @input="clearError"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码（需包含大写+小写+数字）"
            :disabled="loading"
            show-password
            autocomplete="current-password"
            @input="clearError"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            :disabled="!canSubmit"
            class="login-btn"
            size="large"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <p class="login-footer">
        还没有账号？<router-link to="/register">立即注册</router-link>
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { FormInstance, FormRules } from 'element-plus'
import { usernameRule, passwordRule } from '@/utils/validation'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const authError = ref('')

const rules: FormRules = {
  username: [usernameRule],
  password: [passwordRule],
}

const canSubmit = computed(() => form.username.trim() && form.password.trim())

function clearError(): void {
  if (authError.value) authError.value = ''
}

function getErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const data = (err as { response?: { data?: { error?: string; code?: string } } })?.response?.data

  if (status === 429) return '请求过于频繁，请稍后再试'
  if (status === 401) {
    const code = data?.code
    if (code === 'AUTHENTICATION_ERROR') return '用户名或密码错误'
    if (code === 'USER_DISABLED') return '账户已被禁用'
    return '用户名或密码错误'
  }
  if (data?.error) return data.error
  return '网络连接失败，请检查后端服务是否启动'
}

function getFirstAdminPage(): string {
  if (!authStore.isAdmin) {
    return '/'
  }

  // 按优先级检查权限
  const pages = [
    { path: '/admin', permission: 'system:monitor' },
    { path: '/admin/movies', permission: 'movie:read' },
    { path: '/admin/reviews', permission: 'comment:read' },
    { path: '/admin/crawler', permission: 'crawler:task:write' },
    { path: '/admin/failures', permission: 'crawler:failure:manage' },
    { path: '/admin/douban-ids', permission: 'crawler:task:read' },
    { path: '/admin/users', permission: 'user:manage' },
    { path: '/admin/infra', permission: 'system:monitor' },
  ]

  for (const page of pages) {
    if (authStore.checkPermission(page.permission)) {
      return page.path
    }
  }

  return '/403'
}

async function handleLogin(): Promise<void> {
  if (!canSubmit.value || loading.value) return

  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  authError.value = ''
  try {
    await authStore.login({
      username: form.username.trim(),
      password: form.password,
    })
    const redirect = (route.query.redirect as string) || '/'
    // 如果跳转到根路径或管理根路径，管理员自动跳转到第一个有权限的页面
    if (redirect === '/' || redirect === '/admin') {
      const firstPage = getFirstAdminPage()
      router.push(firstPage)
    } else {
      router.push(redirect)
    }
  } catch (err) {
    authError.value = getErrorMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-title {
  font-size: 28px;
  color: #1a1a2e;
  margin: 0 0 4px;
}

.login-subtitle {
  color: #888;
  font-size: 14px;
  margin: 0;
}

.login-alert {
  margin-bottom: 16px;
}

.login-btn {
  width: 100%;
}

.login-footer {
  text-align: center;
  margin-top: 16px;
  color: #888;
  font-size: 14px;
}

.login-footer a {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 500;
}

.login-footer a:hover {
  text-decoration: underline;
}
</style>
