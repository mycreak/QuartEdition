<template>
  <el-container class="admin-layout">
    <el-aside :width="asideWidth" class="admin-sidebar">
      <div class="sidebar-header">
        <span v-if="!isCollapsed" class="sidebar-title">管理后台</span>
        <el-icon class="collapse-btn" :size="20" @click="isCollapsed = !isCollapsed">
          <Fold v-if="!isCollapsed" />
          <Expand v-else />
        </el-icon>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed"
        router
        background-color="#1a1a2e"
        text-color="#ccc"
        active-text-color="#fff"
      >
        <el-menu-item index="/" class="back-home">
          <template #title>< 返回首页</template>
        </el-menu-item>

        <el-divider class="menu-divider" />

        <el-menu-item index="/admin" v-if="authStore.checkPermission('system:monitor')">
          <el-icon><Monitor /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>

        <el-menu-item index="/admin/movies" v-if="authStore.checkPermission('movie:read')">
          <el-icon><VideoCamera /></el-icon>
          <template #title>电影管理</template>
        </el-menu-item>

        <el-menu-item index="/admin/reviews" v-if="authStore.checkPermission('comment:read')">
          <el-icon><ChatLineRound /></el-icon>
          <template #title>评论管理</template>
        </el-menu-item>

        <el-menu-item index="/admin/crawler" v-if="authStore.checkPermission('crawler:task:write')">
          <el-icon><SetUp /></el-icon>
          <template #title>爬虫面板</template>
        </el-menu-item>

        <el-menu-item index="/admin/failures" v-if="authStore.checkPermission('crawler:failure:manage')">
          <el-icon><WarningFilled /></el-icon>
          <template #title>失败任务</template>
        </el-menu-item>

        <el-menu-item index="/admin/douban-ids" v-if="authStore.checkPermission('crawler:task:read')">
          <el-icon><Collection /></el-icon>
          <template #title>豆瓣电影 ID</template>
        </el-menu-item>

        <el-menu-item v-if="authStore.checkPermission('user:manage')" index="/admin/users">
          <el-icon><User /></el-icon>
          <template #title>用户状态管理</template>
        </el-menu-item>

        <el-menu-item v-if="authStore.checkPermission('system:monitor')" index="/admin/infra">
          <el-icon><Tools /></el-icon>
          <template #title>基础设施</template>
        </el-menu-item>
    </el-menu>
    </el-aside>

    <el-container>
      <el-main class="admin-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Monitor, VideoCamera, ChatLineRound, SetUp, WarningFilled, Collection, User, Tools, Fold, Expand, ArrowLeft } from '@element-plus/icons-vue'

const route = useRoute()
const authStore = useAuthStore()

const isCollapsed = ref(false)
const asideWidth = computed(() => (isCollapsed.value ? '64px' : '220px'))

const activeMenu = computed(() => {
  const p = route.path
  if (p.startsWith('/admin/movies')) return '/admin/movies'
  if (p.startsWith('/admin/reviews')) return '/admin/reviews'
  if (p.startsWith('/admin/crawler')) return '/admin/crawler'
  if (p.startsWith('/admin/failures')) return '/admin/failures'
  if (p.startsWith('/admin/douban-ids')) return '/admin/douban-ids'
  if (p.startsWith('/admin/users')) return '/admin/users'
  if (p.startsWith('/admin/infra')) return '/admin/infra'
  return '/admin'
})
</script>

<style scoped>
.admin-layout { min-height: 100vh; }
.admin-sidebar { background: #1a1a2e; overflow-x: hidden; transition: width 0.3s; }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; padding: 16px; color: #fff; }
.sidebar-title { font-size: 16px; font-weight: 600; white-space: nowrap; }
.collapse-btn { cursor: pointer; color: #ccc; transition: color 0.2s; flex-shrink: 0; }
.collapse-btn:hover { color: #fff; }
.admin-content { background: #f5f5f5; padding: 24px; }
.el-menu { border-right: none; }
.el-menu-item.is-active { background: rgba(255, 255, 255, 0.1) !important; }

.back-home { margin-bottom: 4px; }
.back-home:hover { background: rgba(255, 255, 255, 0.08) !important; }
.back-home .el-icon { color: #67c23a; }

.menu-divider { margin: 4px 12px; border-color: rgba(255, 255, 255, 0.1); }
</style>
