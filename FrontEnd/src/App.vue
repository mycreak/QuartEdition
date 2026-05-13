<template>
  <div v-if="showHeader" class="app-shell">
    <AppHeader />
    <main class="app-main">
      <router-view />
    </main>
  </div>
  <main v-else class="auth-shell">
    <router-view />
  </main>
</template>

<script setup lang="ts">
import { computed, watch, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElNotification } from 'element-plus'
import AppHeader from '@/components/layout/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { wsManager } from '@/api/ws'

const route = useRoute()
const authStore = useAuthStore()

const AUTH_ROUTES = ['Login', 'Register']
const ADMIN_PREFIX = '/admin'
const showHeader = computed(() => {
  const name = route.name as string
  if (AUTH_ROUTES.includes(name)) return false
  if (route.path.startsWith(ADMIN_PREFIX)) return false
  return true
})

const pendingFailures = ref<any[]>([])
const isAdminRoute = computed(() => route.path.startsWith(ADMIN_PREFIX))

let unsubFailure: (() => void) | null = null
let unsubWorkerCrash: (() => void) | null = null

function connectWs() {
  if (!authStore.token) return
  wsManager.connect(authStore.token)

  unsubFailure = wsManager.on('task_failure', (msg) => {
    if (isAdminRoute.value) {
      let taskInfo = ''
      try { const t = JSON.parse(msg.task); taskInfo = `[${t.type || ''}] ${(t.douban_id || '')}` } catch { /* */ }
      ElNotification({
        title: '任务失败',
        message: taskInfo ? `${taskInfo}\n${msg.reason}` : msg.reason,
        type: 'error',
        duration: 0,
        showClose: true,
      })
    } else {
      pendingFailures.value.push(msg)
    }
  })

  unsubWorkerCrash = wsManager.on('worker_crash', (msg) => {
    ElNotification({
      title: 'Worker 崩溃',
      message: `Worker ID: ${JSON.stringify(msg.dead)}`,
      type: 'warning',
      duration: 0,
      showClose: true,
    })
  })
}

function disconnectWs() {
  unsubFailure?.()
  unsubWorkerCrash?.()
  unsubFailure = null
  unsubWorkerCrash = null
  wsManager.disconnect()
}

watch(() => authStore.token, (t) => {
  if (t) {
    disconnectWs()
    connectWs()
  } else {
    disconnectWs()
  }
})

watch(isAdminRoute, (isAdmin) => {
  if (isAdmin && pendingFailures.value.length > 0) {
    for (const msg of pendingFailures.value) {
      let taskInfo = ''
      try { const t = JSON.parse(msg.task); taskInfo = `[${t.type || ''}] ${(t.douban_id || '')}` } catch { /* */ }
      ElNotification({
        title: '任务失败 (积压)',
        message: taskInfo ? `${taskInfo}\n${msg.reason}` : msg.reason,
        type: 'error',
        duration: 0,
        showClose: true,
      })
    }
    pendingFailures.value = []
  }
})

onMounted(() => {
  if (authStore.token) connectWs()
})

onUnmounted(() => disconnectWs())
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, 'Noto Sans', sans-serif;
  -webkit-font-smoothing: antialiased;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-shell .app-main {
  flex: 1;
  background: #f5f5f5;
}

.auth-shell {
  min-height: 100vh;
  display: flex;
}
</style>
