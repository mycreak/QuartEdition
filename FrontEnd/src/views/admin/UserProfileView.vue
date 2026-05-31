<template>
  <div class="user-profile-page">
    <div class="page-header">
      <el-button :icon="ArrowLeft" @click="goBack">返回</el-button>
      <h2 class="page-title">用户画像 — {{ profileUser?.display_name || profileUser?.username }}</h2>
    </div>

    <el-card v-loading="profileLoading">
      <template v-if="profileData">
        <!-- 统计概览 -->
        <div class="profile-summary">
          <div class="summary-item">
            <span class="summary-label">用户名</span>
            <span class="summary-value">{{ profileData.user.display_name || profileData.user.username }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">总得分</span>
            <span class="summary-value highlight">{{ profileData.total_score.toFixed(1) }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">标签数</span>
            <span class="summary-value">{{ profileData.tag_count }}</span>
          </div>
        </div>

        <!-- 按维度分组标签 -->
        <template v-if="profileData.tags.length">
          <div v-for="(group, dim) in dimensionData" :key="dim" class="dimension-section">
            <h4 class="dim-title">
              {{ formatDimensionName(dim as string) }}
              <span class="dim-meta">
                CV: {{ group.cv.toFixed(1) }}%
                <template v-if="group.total > 30">
                  （显示前 30 / 共 {{ group.total }}）
                </template>
              </span>
            </h4>
            <div class="dim-tags">
              <el-tag
                v-for="tag in group.tags"
                :key="tag.label"
                size="default"
                class="profile-tag"
                :color="tagColor(tag.score)"
                effect="dark"
              >
                {{ tag.label }}
                <span class="tag-score">{{ tag.score.toFixed(1) }}</span>
              </el-tag>
            </div>
          </div>
        </template>
        <div v-else class="empty-profile">
          <el-empty description="暂无标签数据" />
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { adminUsersApi, type AdminUser, type UserProfileData, type UserProfileTag } from '@/api/admin/users'

const router = useRouter()
const route = useRoute()

const TOP_N = 30

/** 
 * 返回用户画像管理页，保持 tab 状态和分页进度。
 * 
 * 从 UsersView → goToProfile 传入的 query 中提取 tab/page/keyword，
 * 回传确保返回后停留在「用户画像管理」tab + 同一页。
 */
function goBack() {
  const query: Record<string, string> = {}
  const q = route.query
  if (q.tab) query.tab = q.tab as string
  if (q.page) query.page = q.page as string
  if (q.keyword) query.keyword = q.keyword as string
  router.push({ path: '/admin/users', query })
}

const profileUser = ref<AdminUser | null>(null)
const profileData = ref<UserProfileData | null>(null)
const profileLoading = ref(false)

const DIMENSION_LABELS: Record<string, string> = {
  director: '导演',
  actor: '演员',
  genre: '类型',
  era: '年代',
  region: '地区',
  overall: '综合',
  plot: '剧情',
  visual: '视觉',
  narrative: '叙事',
  pacing: '节奏',
}

interface DimensionGroup {
  tags: UserProfileTag[]
  total: number
  cv: number
  mean: number
  stdDev: number
}

/**
 * 计算每个维度：前 30 个标签 + CV 值
 *
 * CV（变异系数）= (标准差 / 均值) × 100
 *   值越高 → 维度内部评分差异越大（标签分散度高）
 *   值越低 → 维度内部评分越一致（标签集中度高）
 */
const dimensionData = computed<Record<string, DimensionGroup>>(() => {
  if (!profileData.value) return {}

  // 1. 按维度分组，按 score 降序排列
  const allTags = profileData.value.tags
  const groups: Record<string, UserProfileTag[]> = {}
  for (const t of allTags) {
    (groups[t.dimension] ||= []).push(t)
  }
  for (const dim of Object.keys(groups)) {
    groups[dim].sort((a, b) => b.score - a.score)
  }

  // 2. 计算每个维度的 CV
  const result: Record<string, DimensionGroup> = {}
  for (const dim of Object.keys(groups)) {
    const all = groups[dim]
    const total = all.length
    const topN = all.slice(0, TOP_N)

    // 全量计算 CV
    const scores = all.map(t => t.score)
    const mean = scores.reduce((s, x) => s + x, 0) / scores.length
    const variance = scores.reduce((s, x) => s + (x - mean) ** 2, 0) / scores.length
    const stdDev = Math.sqrt(variance)
    const cv = mean !== 0 ? (stdDev / mean) * 100 : 0

    result[dim] = {
      tags: topN,
      total,
      cv,
      mean,
      stdDev,
    }
  }

  return result
})

function formatDimensionName(dim: string): string {
  return DIMENSION_LABELS[dim] || dim
}

function tagColor(score: number): string {
  if (score >= 8) return '#409eff'
  if (score >= 4) return '#67c23a'
  if (score >= 2) return '#e8a838'
  return '#909399'
}

async function fetchProfile(userId: number) {
  profileLoading.value = true
  profileData.value = null
  try {
    const res = await adminUsersApi.profile(userId)
    profileData.value = res.data
    profileUser.value = res.data.user
  } catch {
    ElMessage.error('加载用户画像失败')
  } finally {
    profileLoading.value = false
  }
}

onMounted(() => {
  const userId = Number(route.params.id)
  if (userId) {
    fetchProfile(userId)
  }
})
</script>

<style scoped>
.user-profile-page {
  max-width: 1100px;
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  color: #1a1a2e;
  margin: 0;
}

/* 画像摘要 */
.profile-summary {
  display: flex;
  gap: 24px;
  padding: 20px 24px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 24px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 16px;
  color: #303133;
  font-weight: 600;
}

.summary-value.highlight {
  color: #409eff;
  font-size: 18px;
}

/* 维度分组 */
.dimension-section {
  margin-bottom: 20px;
}

.dim-title {
  font-size: 14px;
  color: #606266;
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.dim-meta {
  font-size: 12px;
  color: #909399;
  font-weight: 400;
}

.dim-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.profile-tag {
  font-size: 13px;
}

.tag-score {
  margin-left: 4px;
  opacity: 0.85;
  font-size: 11px;
}
</style>
