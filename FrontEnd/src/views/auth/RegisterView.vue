<template>
  <div class="register-page">
    <el-card class="register-card" shadow="always">
      <div class="register-header">
        <h1 class="register-title">创建账号</h1>
        <p class="register-subtitle">加入 QuartEdition 数据平台</p>
      </div>

      <el-alert
        v-if="successMsg"
        :title="successMsg"
        type="success"
        :closable="true"
        show-icon
        @close="successMsg = ''"
        class="register-alert"
      />

      <el-alert
        v-if="authError"
        :title="authError"
        type="error"
        :closable="true"
        show-icon
        @close="authError = ''"
        class="register-alert"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleRegister"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="6-32 位字母数字下划线"
            :disabled="loading"
            autocomplete="username"
            @input="clearError"
          />
        </el-form-item>

        <el-form-item label="昵称" prop="display_name">
          <el-input
            v-model="form.display_name"
            placeholder="你希望被看到的名称（选填）"
            :disabled="loading"
            @input="clearError"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="6-128 位，需包含大写+小写+数字"
            :disabled="loading"
            show-password
            autocomplete="new-password"
            @input="clearError"
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            :disabled="loading"
            show-password
            autocomplete="new-password"
            @input="clearError"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            :disabled="!canSubmit"
            class="register-btn"
            size="large"
          >
            注册
          </el-button>
        </el-form-item>
      </el-form>

      <p class="register-footer">
        已有账号？<router-link to="/login">返回登录</router-link>
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { validateUsername, validatePassword, validateConfirmPassword } from '@/utils/validation'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '', display_name: '', confirmPassword: '' })
const loading = ref(false)
const authError = ref('')
const successMsg = ref('')

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { validator: validateUsername, trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { validator: validatePassword, trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirmPassword(() => form.password), trigger: 'blur' },
  ],
}

const canSubmit = computed(
  () =>
    form.username.trim() &&
    form.password &&
    form.confirmPassword &&
    form.password === form.confirmPassword
)

watch(() => form.password, () => {
  if (form.confirmPassword) {
    formRef.value?.validateField('confirmPassword')
  }
})

function clearError(): void {
  if (authError.value) authError.value = ''
  if (successMsg.value) successMsg.value = ''
}

function getErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const data = (err as { response?: { data?: { error?: string; code?: string } } })?.response?.data

  if (status === 409 && data?.code === 'DUPLICATE') return '用户名已存在，请换一个'
  if (status === 400 && data?.error) return data.error
  if (data?.error) return data.error
  return '网络连接失败，请检查后端服务是否启动'
}

async function handleRegister(): Promise<void> {
  if (!canSubmit.value || loading.value) return

  if (form.password !== form.confirmPassword) {
    authError.value = '两次输入的密码不一致'
    return
  }

  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  authError.value = ''
  successMsg.value = ''
  try {
    await authStore.register({
      username: form.username.trim(),
      password: form.password,
      display_name: form.display_name.trim() || undefined,
    })
    successMsg.value = '注册成功！即将跳转登录页...'
    formRef.value?.resetFields()
    setTimeout(() => {
      router.push('/login')
    }, 1500)
  } catch (err) {
    authError.value = getErrorMessage(err)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  padding: 20px;
}

.register-card {
  width: 100%;
  max-width: 440px;
}

.register-header {
  text-align: center;
  margin-bottom: 24px;
}

.register-title {
  font-size: 24px;
  color: #1a1a2e;
  margin: 0 0 4px;
}

.register-subtitle {
  color: #888;
  font-size: 14px;
  margin: 0;
}

.register-alert {
  margin-bottom: 16px;
}

.register-btn {
  width: 100%;
}

.register-footer {
  text-align: center;
  margin-top: 16px;
  color: #888;
  font-size: 14px;
}

.register-footer a {
  color: var(--el-color-primary);
  text-decoration: none;
  font-weight: 500;
}

.register-footer a:hover {
  text-decoration: underline;
}
</style>
