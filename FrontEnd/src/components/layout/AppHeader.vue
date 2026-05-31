<template>
  <el-header class="app-header" :class="{ 'is-admin': isAdminRoute }" height="56px">
    <div class="header-left">
      <router-link to="/" class="logo">QuartEdition</router-link>
    </div>

    <div class="header-right">
      <template v-if="authStore.isLoggedIn">
        <el-button
          v-if="authStore.isAdmin"
          text
          class="admin-entry"
          @click="isAdminRoute ? $router.push('/') : $router.push('/admin')"
        >
          {{ isAdminRoute ? '返回用户端' : '管理后台' }}
        </el-button>

        <el-dropdown trigger="click">
          <span class="user-trigger">
            <div class="user-avatar" v-if="authStore.user?.avatar_url">
              <img :src="authStore.user.avatar_url" alt="头像" />
            </div>
            <el-icon v-else><UserFilled /></el-icon>
            <span class="user-name">{{ authStore.user?.display_name || authStore.user?.username }}</span>
            <el-tag
              v-if="authStore.isAdmin"
              size="small"
              type="warning"
              effect="dark"
            >
              管理员
            </el-tag>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="!isAdminRoute" @click="router.push('/profile')">
                <el-icon><User /></el-icon>
                个人中心
              </el-dropdown-item>
              <el-dropdown-item :class="{ 'is-divided': !isAdminRoute }" @click="handleLogout">
                <el-icon><SwitchButton /></el-icon>
                退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>

      <template v-else>
        <el-button text class="nav-btn" @click="$router.push('/login')">
          登录
        </el-button>
        <el-button text class="nav-btn" @click="$router.push('/register')">
          注册
        </el-button>
      </template>
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { UserFilled, SwitchButton, User } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

// 判断当前是否在管理后台页面
const isAdminRoute = computed(() => route.path.startsWith('/admin'))

function handleLogout(): void {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #e3f2fd;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.app-header.is-admin {
  background: #1a1a2e;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.header-left {
  display: flex;
  align-items: center;
}

.logo {
  font-size: 18px;
  font-weight: 700;
  color: #1976d2;
  text-decoration: none;
  letter-spacing: 0.5px;
}

.app-header.is-admin .logo {
  color: #fff;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-btn {
  color: #424242 !important;
  font-size: 14px;
}

.nav-btn:hover {
  color: #1976d2 !important;
}

.app-header.is-admin .nav-btn {
  color: #ccc !important;
}

.app-header.is-admin .nav-btn:hover {
  color: #fff !important;
}

.admin-entry {
  color: #424242 !important;
  border: 1px solid rgba(25, 118, 210, 0.3);
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 13px;
}

.admin-entry:hover {
  color: #1976d2 !important;
  border-color: rgba(25, 118, 210, 0.5);
}

.app-header.is-admin .admin-entry {
  color: #ccc !important;
  border: 1px solid rgba(255, 255, 255, 0.25);
}

.app-header.is-admin .admin-entry:hover {
  color: #fff !important;
  border-color: rgba(255, 255, 255, 0.5);
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #424242;
  font-size: 14px;
  transition: color 0.2s;
}

.user-trigger:hover {
  color: #1976d2;
}

.app-header.is-admin .user-trigger {
  color: #ccc;
}

.app-header.is-admin .user-trigger:hover {
  color: #fff;
}

.user-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  overflow: hidden;
}

.user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-name {
  color: #424242;
}

.app-header.is-admin .user-name {
  color: #fff;
}
</style>
