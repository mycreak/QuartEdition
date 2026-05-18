<template>
  <div v-loading="loading" class="admin-movie-detail">
    <div class="detail-nav">
      <el-button text @click="$router.push('/admin/movies')">← 返回电影列表</el-button>
      <el-button text @click="$router.push(`/movies/${movieId}`)" v-if="detail && detail.movie.is_published">查看用户端 →</el-button>
    </div>

    <ErrorAlert :message="error" @close="error = ''" />

    <template v-if="detail">
      <div class="detail-hero">
        <div class="detail-poster" @click="handlePosterUpload" :class="{'clickable': authStore.checkPermission('movie:manage')}">
          <el-image v-if="detail?.movie?.poster_url" :src="detail.movie.poster_url" fit="contain" referrerpolicy="no-referrer" class="poster-img">
            <template #error><div class="poster-placeholder"><el-icon :size="40"><VideoCamera /></el-icon></div></template>
          </el-image>
          <div v-else class="poster-placeholder"><el-icon :size="40"><VideoCamera /></el-icon></div>
          <div class="poster-mask" v-if="authStore.checkPermission('movie:manage')">
            <el-icon :size="20"><Upload /></el-icon>
            <span>点击更换海报</span>
          </div>
        </div>
        <div class="detail-info">
          <h1 class="detail-title">{{ detail.movie?.title }}</h1>
          <div class="detail-meta">
            <span class="meta-item">豆瓣 ID: {{ detail.movie?.douban_id || '—' }}</span>
            <span v-if="detail.movie?.release_year" class="meta-item">{{ detail.movie.release_year }}</span>
            <span v-if="detail.rating?.average" class="meta-item rating-star">
              <el-icon :size="16"><StarFilled /></el-icon>{{ formatRating(detail.rating.average) }}
              <span class="rating-count">({{ formatCount(detail.rating.count) }}人评分)</span>
            </span>
          </div>

          <div v-if="detail.genres?.length" class="tag-row">
            <el-tag v-for="g in detail.genres" :key="g.id" size="small" class="genre-tag" closable @close="removeGenre(g)">{{ g.name }}</el-tag>
            <el-button v-if="authStore.checkPermission('movie:manage')" size="small" circle @click="openAddGenre"><el-icon><Plus /></el-icon></el-button>
          </div>

          <div v-if="detail.regions?.length" class="tag-row">
            <el-tag v-for="r in detail.regions" :key="r.id" size="small" type="info" closable @close="removeRegion(r)">{{ r.name }}</el-tag>
            <el-button v-if="authStore.checkPermission('movie:manage')" size="small" circle @click="openAddRegion"><el-icon><Plus /></el-icon></el-button>
          </div>

          <div class="status-row">
            <el-tag :type="detail.movie?.is_published ? 'success' : 'info'" size="medium">{{ detail.movie?.is_published ? '已上架' : '已下架' }}</el-tag>
            <el-button v-if="authStore.checkPermission('movie:manage')" size="small" :type="detail.movie?.is_published ? 'danger' : 'success'" @click="togglePublish" :loading="publishing">{{ detail.movie?.is_published ? '下架' : '上架' }}</el-button>
            <el-button v-if="authStore.checkPermission('movie:manage')" size="small" type="primary" @click="openEditBasic"><el-icon><Edit /></el-icon> 编辑信息</el-button>
          </div>
        </div>

        <div v-if="detail.rating" class="detail-rating">
          <div class="rating-big">
            <span class="rating-score">{{ formatRating(detail.rating.average) }}</span>
            <span class="rating-total">{{ formatCount(detail.rating.count) }}人评分</span>
            <el-button v-if="authStore.checkPermission('movie:manage')" size="small" text type="primary" @click="openEditRating" style="margin-top:4px">编辑评分</el-button>
          </div>
          <div v-if="detail.rating?.distribution" class="rating-bars">
            <div v-for="i in 5" :key="i" class="bar-row">
              <span class="bar-label">{{ i }}星</span>
              <el-progress :percentage="getStarPercent(6 - i)" :show-text="false" :stroke-width="8" color="#e8a838" />
            </div>
          </div>
        </div>
      </div>

      <el-divider />

      <div v-if="detail.directors?.length || authStore.checkPermission('movie:manage')" class="section">
        <h2 class="section-title">导演</h2>
        <div class="person-list">
          <span v-for="d in detail.directors" :key="d.id" class="person-item">
            {{ d.name }}
            <el-icon v-if="authStore.checkPermission('movie:manage')" class="delete-icon" @click="removeCredit(d.id, 'director')"><Close /></el-icon>
          </span>
          <el-button v-if="authStore.checkPermission('movie:manage')" size="small" circle @click="openAddCredit('director')"><el-icon><Plus /></el-icon></el-button>
        </div>
      </div>

      <div v-if="detail.actors?.length || authStore.checkPermission('movie:manage')" class="section">
        <h2 class="section-title">演员</h2>
        <div class="person-list">
          <span v-for="a in detail.actors" :key="a.id" class="person-item">
            {{ a.name }}
            <el-icon v-if="authStore.checkPermission('movie:manage')" class="delete-icon" @click="removeCredit(a.id, 'actor')"><Close /></el-icon>
          </span>
          <el-button v-if="authStore.checkPermission('movie:manage')" size="small" circle @click="openAddCredit('actor')"><el-icon><Plus /></el-icon></el-button>
        </div>
      </div>

      <div v-if="(detail.crew && Object.keys(detail.crew).length) || authStore.checkPermission('movie:manage')" class="section">
        <h2 class="section-title">演职人员</h2>
        <div v-for="(members, role) in detail.crew" :key="role" class="crew-group">
          <span class="crew-role">{{ formatCrewRole(role as string) }}:</span>
          <span v-for="m in members" :key="m.id" class="person-item-inline">
            {{ m.name }}
            <el-icon v-if="authStore.checkPermission('movie:manage')" class="delete-icon" @click="removeCredit(m.id, role as string)"><Close /></el-icon>
          </span>
          <el-button v-if="authStore.checkPermission('movie:manage')" size="small" circle @click="openAddCredit(role as string)"><el-icon><Plus /></el-icon></el-button>
        </div>
      </div>

      <!-- AI 总结 -->
      <div class="section">
        <h2 class="section-title">
          <el-icon style="color: #409eff; margin-right: 4px;"><MagicStick /></el-icon>
          AI 剧情总结
        </h2>
        <p v-if="detail.ai_summary" class="ai-summary">{{ detail.ai_summary }}</p>
        <p v-else class="ai-summary empty">暂无AI总结</p>
      </div>

      <!-- AI 标签 -->
      <div class="section">
        <h2 class="section-title">
          <el-icon style="color: #67c23a; margin-right: 4px;"><CollectionTag /></el-icon>
          AI 标签
        </h2>
        <div v-if="detail.ai_tags?.length" class="tag-row">
          <el-tag 
            v-for="tag in detail.ai_tags" 
            :key="tag" 
            size="small" 
            type="success"
            effect="light"
          >
            {{ tag }}
          </el-tag>
        </div>
        <p v-else class="empty">暂无AI标签</p>
      </div>

      <!-- 短评词云 -->
      <div class="section">
        <h2 class="section-title">
          <el-icon style="color: #8b5cf6; margin-right: 4px;"><ChatDotRound /></el-icon>
          短评词云
        </h2>
        <CommentWordCloud 
          :words="wordCloudWords" 
          :loading="wordCloudLoading" 
          :error="wordCloudError"
          @word-click="handleWordClick"
          @retry="fetchWordCloud(movieId)"
        />
      </div>

      <el-divider />

      <el-card class="related-section">
        <template #header><span class="section-title">关联数据</span></template>
        <div class="related-grid">
          <div class="related-item">
            <span class="related-label">长评</span>
            <span class="related-value">{{ localReviewCount }} 条</span>
            <el-button size="small" text @click="goToReviews('reviews')">查看</el-button>
          </div>
          <div class="related-item">
            <span class="related-label">短评</span>
            <span class="related-value">{{ localCommentCount }} 条</span>
            <el-button size="small" text @click="goToReviews('comments')">查看</el-button>
          </div>
        </div>
      </el-card>
    </template>

    <div v-if="!loading && !detail && !error" class="not-found">
      <el-empty description="未找到该电影" />
    </div>

    <!-- 裁剪海报弹窗 -->
    <el-dialog
      v-model="cropperVisible"
      title="裁剪海报"
      width="600px"
      :close-on-click-modal="false"
      @close="resetCropper"
    >
      <div class="cropper-container">
        <vue-cropper
          ref="cropperRef"
          :img="originImageUrl"
          :output-type="'webp'"
          :output-size="0.8"
          :auto-crop="true"
          :auto-crop-width="400"
          :auto-crop-height="600"
          :fixed="true"
          :fixed-number="[2,3]"
          :center-box="true"
          :info="true"
          :can-move="true"
          :can-scale="true"
        />
      </div>
      <div v-if="uploadError" class="upload-error">{{ uploadError }}</div>
      <template #footer>
        <el-button @click="cropperVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirmCrop" :loading="uploading">
          确认并上传
        </el-button>
      </template>
    </el-dialog>

    <input
      ref="fileInputRef"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      style="display: none"
      @change="handleFileChange"
    />

    <!-- ═══════ 编辑基本信息弹窗 ═══════ -->
    <el-dialog v-model="editBasicVisible" title="编辑电影信息" width="480px">
      <el-form :model="editBasicForm" label-position="top">
          <el-form-item label="片名"><el-input v-model="editBasicForm.title" /></el-form-item>
          <el-form-item label="豆瓣 ID"><el-input :value="detail?.movie?.douban_id || '—'" disabled /></el-form-item>
          <el-form-item label="上映年份"><el-input v-model="editBasicForm.release_year" placeholder="请输入上映年份" maxlength="4" style="width:100%" /></el-form-item>
        
      </el-form>
      <template #footer>
        <el-button @click="editBasicVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditBasic" :loading="editBasicSaving">保存</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 添加演职人员弹窗 ═══════ -->
    <el-dialog v-model="addCreditVisible" :title="`添加${formatCrewRole(addCreditRole)}`" width="480px">
      <el-form :model="addCreditForm" label-position="top">
        <el-form-item label="添加方式">
          <el-radio-group v-model="addCreditMode" style="width: 100%">
            <el-radio label="select">选择已有人员</el-radio>
            <el-radio label="manual">手动新增人员</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 选择已有人员模式 -->
        <template v-if="addCreditMode === 'select'">
          <el-form-item label="人员">
            <el-autocomplete v-model="addCreditPersonName" :fetch-suggestions="searchPeople" placeholder="搜索已有人员姓名或输入 person_id" style="width:100%" clearable @select="onPersonSelect" />
          </el-form-item>
          <el-form-item label="豆瓣ID">
            <el-input :value="addCreditPersonDoubanId || '暂无douban_id'" placeholder="搜索选择人员后自动填充豆瓣ID" style="width:100%" disabled />
          </el-form-item>
        </template>

        <!-- 手动新增人员模式 -->
        <template v-if="addCreditMode === 'manual'">
          <el-form-item label="人员姓名" required>
            <el-input v-model="addCreditManualForm.name" placeholder="请输入人员姓名" clearable />
          </el-form-item>
          <el-form-item label="豆瓣ID（可选）">
            <el-input v-model="addCreditManualForm.douban_id" placeholder="请输入豆瓣人员ID（选填）" clearable />
            <div class="form-hint">填写豆瓣ID可避免后续爬虫重复创建该人员</div>
          </el-form-item>
        </template>


      </el-form>
      <template #footer>
        <el-button @click="addCreditVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddCredit" :loading="addCreditSaving">添加</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 添加类型弹窗 ═══════ -->
    <el-dialog v-model="addGenreVisible" title="添加电影类型" width="400px">
      <el-select v-model="addGenreTypeNum" placeholder="选择类型" style="width: 100%" filterable>
        <el-option v-for="t in filteredTypeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
      </el-select>
      <template #footer>
        <el-button @click="addGenreVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddGenre" :loading="addGenreSaving">添加</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 添加地区弹窗 ═══════ -->
    <el-dialog v-model="addRegionVisible" title="添加地区" width="400px">
      <el-form :model="addRegionForm" label-position="top">
        <el-form-item label="地区">
        <el-select v-model="addRegionForm.region_id" placeholder="选择现有地区" style="width: 100%" filterable :loading="allRegionsLoading">
          <el-option v-for="r in filteredRegionOptions" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        </el-form-item>
        <el-form-item label="添加新地区">
          <el-input v-model="addRegionForm.name" placeholder="输入新地区名称，如中国香港" />
          <div class="form-hint">若上方未找到需要的地区，可在此输入新名称添加</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addRegionVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddRegion" :loading="addRegionSaving">添加</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 编辑评分弹窗 ═══════ -->
    <el-dialog v-model="editRatingVisible" title="编辑评分" width="380px">
      <el-form :model="editRatingForm" label-position="top">
        <el-form-item label="评分"><el-input-number v-model="editRatingForm.average" :min="0" :max="10" :precision="1" :step="0.1" style="width:100%" /></el-form-item>
        <el-form-item label="评分人数"><el-input-number v-model="editRatingForm.count" :min="0" :step="1" style="width:100%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editRatingVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditRating" :loading="editRatingSaving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import client from '@/api/client'
import { adminMoviesApi } from '@/api/admin/movies'
import { adminReviewsApi } from '@/api/admin/reviews'
import type { MovieDetail, Person } from '@/types/movie'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import { formatRating, formatCount, formatCrewRole } from '@/utils/format'
import { StarFilled, VideoCamera, Edit, Plus, Close, Upload, MagicStick, CollectionTag, ChatDotRound } from '@element-plus/icons-vue'
import { VueCropper } from 'vue-cropper/next'
import 'vue-cropper/next/dist/index.css'
import CommentWordCloud from '@/components/common/CommentWordCloud.vue'
import { moviesApi } from '@/api/movies'
import type { WordCloudItem } from '@/types/movie'

const TYPE_MAP: Record<number, string> = {
  1: '纪录片', 2: '传记', 3: '犯罪', 4: '历史', 5: '动作', 6: '情色', 7: '歌舞', 8: '儿童', 10: '悬疑', 11: '剧情',
  12: '灾难', 13: '爱情', 14: '音乐', 15: '冒险', 16: '奇幻', 17: '科幻', 18: '运动', 19: '惊悚', 20: '恐怖',
  22: '战争', 23: '短片', 24: '喜剧', 25: '动画', 27: '西部', 28: '家庭', 29: '武侠', 30: '古装', 31: '黑色电影',
}

const typeOptions = Object.entries(TYPE_MAP).map(([num, name]) => ({ type_num: Number(num), type_name: name }))

const roleTypes = ['director', 'actor', 'writer', 'producer', 'art_director', 'music', 'other']

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// 过滤已经关联的类型，避免重复添加
const filteredTypeOptions = computed(() => {
  const existingTypeIds = new Set((detail.value?.genres || []).map(g => g.id))
  return typeOptions.filter(t => !existingTypeIds.has(t.type_num))
})

// 过滤已经关联的地区，避免重复添加
const filteredRegionOptions = computed(() => {
  const existingRegionIds = new Set((detail.value?.regions || []).map(r => r.id))
  return allRegions.value.filter(r => !existingRegionIds.has(r.id))
})

const movieId = Number(route.params.id)
const detail = ref<MovieDetail | null>(null)
const loading = ref(false)
const error = ref('')
const publishing = ref(false)

const localReviewCount = ref(0)
const localCommentCount = ref(0)

/* ── 编辑基本信息 ── */
const editBasicVisible = ref(false)
const editBasicSaving = ref(false)
const editBasicForm = ref({ title: '', release_year: undefined as number | undefined })

/* ── 海报上传裁剪 ── */
  const fileInputRef = ref<HTMLInputElement | null>(null)
  const cropperRef = ref<InstanceType<typeof VueCropper> | null>(null)
  const cropperVisible = ref(false)
  const originImageUrl = ref('')
  const uploading = ref(false)
  const uploadError = ref('')

  const handlePosterUpload = () => {
    if (!authStore.checkPermission('movie:manage')) return
    fileInputRef.value?.click()
  }

  const handleFileChange = (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return

    if (file.size > 5 * 1024 * 1024) {
      ElMessage.error('海报大小不能超过5MB')
      resetFileInput()
      return
    }

    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      ElMessage.error('仅支持png/jpg/webp格式的图片')
      resetFileInput()
      return
    }

    originImageUrl.value = URL.createObjectURL(file)
    uploadError.value = ''
    cropperVisible.value = true
    resetFileInput()
  }

  const handleConfirmCrop = async () => {
    if (!cropperRef.value || !detail.value?.movie?.id) return

    uploading.value = true
    uploadError.value = ''

    try {
      cropperRef.value.getCropBlob(async (blob: Blob) => {
        try {
          const file = new File([blob], 'poster.webp', { type: 'image/webp' })
          // 先上传到存储
          const uploadRes = await adminMoviesApi.uploadPoster(file)
          const posterUrl = uploadRes.data.data.poster_url
          // 然后更新电影信息
          const movieId = parseInt(route.params.id as string)
          if (isNaN(movieId)) {
            throw new Error('无效的电影ID')
          }
          const updateRes = await adminMoviesApi.update(movieId, {
            poster_url: posterUrl
          })
          if (updateRes.data.movie && detail.value) {
            detail.value.movie = updateRes.data.movie
            ElMessage.success('海报更新成功')
            cropperVisible.value = false
          }
        } catch (err: any) {
          const msg = err.response?.data?.error || '海报上传失败'
          uploadError.value = msg
          ElMessage.error(msg)
        } finally {
          uploading.value = false
        }
      })
    } catch (err: any) {
      const msg = '海报裁剪失败'
      uploadError.value = msg
      ElMessage.error(msg)
      uploading.value = false
    }
  }

  const resetFileInput = () => {
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
  }

  const resetCropper = () => {
    if (originImageUrl.value) {
      URL.revokeObjectURL(originImageUrl.value)
      originImageUrl.value = ''
    }
    cropperRef.value = null
    uploadError.value = ''
  }

  /* ── 添加演职人员 ── */
const addCreditVisible = ref(false)
const addCreditSaving = ref(false)
const addCreditRole = ref('')
const addCreditRoleAssign = ref('')
const addCreditPersonName = ref('')
const addCreditPersonDoubanId = ref('')
const addCreditForm = ref({ person_id: undefined as number | undefined })
const addCreditMode = ref<'select' | 'manual'>('select')
const addCreditManualForm = ref({ name: '', douban_id: '' })

/* ── 添加类型 ── */
const addGenreVisible = ref(false)
const addGenreSaving = ref(false)
const addGenreTypeNum = ref<number | ''>('')

/* ── 添加地区 ── */
const addRegionVisible = ref(false)
const addRegionSaving = ref(false)
const allRegions = ref<{ id: number; name: string }[]>([])
const allRegionsLoading = ref(false)
const addRegionForm = ref({ 
  region_id: undefined as number | undefined,
  name: ''
})

/* ── 编辑评分 ── */
const editRatingVisible = ref(false)
const editRatingSaving = ref(false)
const editRatingForm = ref({ average: 0, count: 0 })

/* ── 收集所有已知人员用于搜索 ── */
const knownPeople = computed<Person[]>(() => {
  if (!detail.value) return []
  const seen = new Set<number>()
  const result: Person[] = []
  for (const p of [...(detail.value.directors || []), ...(detail.value.actors || [])]) {
    if (!seen.has(p.id)) { seen.add(p.id); result.push(p) }
  }
  for (const members of Object.values(detail.value.crew || {})) {
    for (const p of members) {
      if (!seen.has(p.id)) { seen.add(p.id); result.push(p) }
    }
  }
  return result
})

// 获取当前要添加的角色下已存在的人员ID，用于搜索排除
const currentRoleExistingPersonIds = computed(() => {
  if (!detail.value || !addCreditRole.value) return new Set<number>()
  const role = addCreditRole.value
  if (role === 'director') {
    return new Set((detail.value.directors || []).map(p => p.id))
  } else if (role === 'actor') {
    return new Set((detail.value.actors || []).map(p => p.id))
  } else {
    // 其他自定义crew角色
    return new Set((detail.value.crew?.[role] || []).map((p: Person) => p.id))
  }
})

function getStarPercent(stars: number): number {
  if (!detail.value?.rating?.distribution) return 0
  const { count, distribution } = detail.value.rating
  if (!count) return 0
  return Math.round((Number(distribution[String(stars)]) || 0) / count * 100)
}

/* ── 词云 ── */
const wordCloudWords = ref<WordCloudItem[]>([])
const wordCloudLoading = ref(false)
const wordCloudError = ref('')

async function fetchWordCloud(movieId: number): Promise<void> {
  wordCloudLoading.value = true
  wordCloudError.value = ''
  try {
    const res = await moviesApi.getWordCloud(movieId)
    if (res.data.success) {
      wordCloudWords.value = res.data.data.words
    } else {
      wordCloudError.value = '词云生成失败'
    }
  } catch (err: any) {
    wordCloudError.value = err.response?.data?.error || '加载失败，请稍后重试'
    wordCloudWords.value = []
  } finally {
    wordCloudLoading.value = false
  }
}

async function loadDetail() {
  if (!movieId) { error.value = '无效的电影 ID'; return }
  loading.value = true; error.value = ''
  try {
    const res = await adminMoviesApi.detail(movieId)
    detail.value = res.data
    fetchLocalCounts()
    // 页面加载时预加载所有地区列表，避免打开弹窗时才加载导致空白
    fetchAllRegions()
    fetchWordCloud(movieId)
  } catch (e: any) {
    error.value = e?.response?.status === 404 ? '电影不存在' : '加载失败，请检查后端服务'
  } finally { loading.value = false }
}

async function fetchLocalCounts() {
  try {
    const [revRes, comRes] = await Promise.all([
      adminReviewsApi.reviews({ movie_id: movieId, page_size: 1 }),
      adminReviewsApi.comments({ movie_id: movieId, page_size: 1 }),
    ])
    localReviewCount.value = revRes.data.total
    localCommentCount.value = comRes.data.total
  } catch { /* ignore */ }
}

function handleWordClick(word: WordCloudItem): void {
  router.push({ path: '/admin/reviews', query: { tab: 'comments', movie_id: String(movieId) } })
}

function goToReviews(tab: string) {
  router.push({ path: '/admin/reviews', query: { tab, movie_id: String(movieId) } })
}

async function togglePublish() {
  if (!detail.value?.movie) return
  publishing.value = true
  try {
    const movie = detail.value.movie
    const api = movie.is_published ? adminMoviesApi.unpublish : adminMoviesApi.publish
    await api(movie.id)
    movie.is_published = !movie.is_published
    ElMessage.success(movie.is_published ? '已上架' : '已下架')
  } catch { ElMessage.error('操作失败') }
  finally { publishing.value = false }
}

/* ── 编辑基本信息 ── */
function openEditBasic() {
  const m = detail.value?.movie
  editBasicForm.value = {
    title: m?.title || '',
    release_year: m?.release_year
  }
  editBasicVisible.value = true
}

async function submitEditBasic() {
  if (!detail.value?.movie) return


  editBasicSaving.value = true
  try {
    if (isNaN(movieId)) {
      ElMessage.error('无效的电影ID')
      return
    }
    const res = await adminMoviesApi.update(movieId, {
      title: editBasicForm.value.title || undefined,
      release_year: editBasicForm.value.release_year,
    })
    if (res.data.movie && detail.value) {
      detail.value.movie = res.data.movie
    }
    ElMessage.success('电影信息已更新')
    editBasicVisible.value = false
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '保存失败') }
  finally { editBasicSaving.value = false }
}

/* ── 演职人员 ── */
function openAddCredit(role: string) {
  addCreditRole.value = role
  addCreditRoleAssign.value = role
  addCreditPersonName.value = ''
  addCreditPersonDoubanId.value = ''
  addCreditForm.value = { person_id: undefined }
  addCreditMode.value = 'select'
  addCreditManualForm.value = { name: '', douban_id: '' }
  addCreditVisible.value = true
}

function searchPeople(query: string, cb: (items: { value: string; label: string; person: Person }[]) => void) {
  const q = query.toLowerCase()
  const existingIds = currentRoleExistingPersonIds.value
  const items = knownPeople.value
    .filter(p => 
      (p.name.toLowerCase().includes(q) || String(p.id).includes(q)) 
      && !existingIds.has(p.id) // 排除当前角色已添加的人员
    )
    .slice(0, 20)
    .map(p => ({ value: p.name, label: `${p.name} (id:${p.id})`, person: p }))
  cb(items)
}

function onPersonSelect(item: { person: Person }) {
  addCreditForm.value.person_id = item.person.id
  addCreditPersonName.value = item.person.name
  addCreditPersonDoubanId.value = item.person.douban_id || ''
}

async function submitAddCredit() {
  addCreditSaving.value = true
  try {
    if (addCreditMode.value === 'select') {
      // 选择已有人员模式
      if (!addCreditForm.value.person_id) { 
        ElMessage.warning('请选择或输入人员 ID')
        return
      }
      await adminMoviesApi.addCredit(movieId, {
        person_id: addCreditForm.value.person_id,
        role_type: addCreditRoleAssign.value,
      })
    } else {
      // 手动新增人员模式
      if (!addCreditManualForm.value.name.trim()) {
        ElMessage.warning('请输入人员姓名')
        return
      }
      await adminMoviesApi.addCreditManual(movieId, {
        name: addCreditManualForm.value.name.trim(),
        douban_id: addCreditManualForm.value.douban_id.trim() || undefined,
        role_type: addCreditRoleAssign.value,
      })
    }
    ElMessage.success('演职人员已添加')
    addCreditVisible.value = false
    await loadDetail()
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '添加失败') }
  finally { addCreditSaving.value = false }
}

async function removeCredit(personId: number, roleType: string) {
  try {
    await ElMessageBox.confirm(
      `确定移除该${formatCrewRole(roleType)}吗？`,
      '确认移除',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    await adminMoviesApi.removeCredit(movieId, { person_id: personId, role_type: roleType })
    ElMessage.success('已移除')
    await loadDetail()
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '移除失败') }
}

/* ── 类型 ── */
function openAddGenre() {
  const existingIds = new Set((detail.value?.genres || []).map(g => g.id))
  addGenreTypeNum.value = typeOptions.find(t => !existingIds.has(t.type_num))?.type_num || ''
  addGenreVisible.value = true
}

async function submitAddGenre() {
  if (!addGenreTypeNum.value) { ElMessage.warning('请选择类型'); return }
  addGenreSaving.value = true
  try {
    await adminMoviesApi.addGenre(movieId, { type_num: addGenreTypeNum.value as number })
    ElMessage.success('类型已添加')
    addGenreVisible.value = false
    await loadDetail()
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '添加失败') }
  finally { addGenreSaving.value = false }
}

async function removeGenre(g: { id: number; name: string }) {
  try {
    await ElMessageBox.confirm(`确定移除类型「${g.name}」吗？`, '确认移除', { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await adminMoviesApi.removeGenre(movieId, g.id)
    if (detail.value) detail.value.genres = (detail.value.genres || []).filter(x => x.id !== g.id)
    ElMessage.success('已移除')
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '移除失败') }
}

/* ── 地区 ── */
async function fetchAllRegions() {
  allRegionsLoading.value = true
  try {
    const res = await client.get<{ id: number; name: string }[]>('/admin/regions')
    // 接口直接返回数组，不需要取items字段
    allRegions.value = res.data || []
  } catch {
    ElMessage.error('加载地区列表失败')
  } finally {
    allRegionsLoading.value = false
  }
}

function openAddRegion() {
  addRegionForm.value = { region_id: undefined, name: '' }
  // 已经加载过地区列表就不用重复请求了
  if (allRegions.value.length === 0) {
    fetchAllRegions()
  }
  addRegionVisible.value = true
}

// 地区字段联动逻辑
watch(() => addRegionForm.value.region_id, (newVal) => {
  if (newVal !== undefined && addRegionForm.value.name.trim()) {
    addRegionForm.value.name = ''
  }
})

watch(() => addRegionForm.value.name, (newVal) => {
  if (newVal.trim() && addRegionForm.value.region_id !== undefined) {
    addRegionForm.value.region_id = undefined
  }
})

async function submitAddRegion() {
  if (!addRegionForm.value.region_id && !addRegionForm.value.name.trim()) { 
    ElMessage.warning('请选择现有地区或输入新地区名称'); 
    return 
  }
  
  addRegionSaving.value = true
  try {
      let regionId = addRegionForm.value.region_id
      let extraMessage = ''
      // 如果输入了新地区名称，先创建新地区
      if (addRegionForm.value.name.trim()) {
        const createRes = await client.post<{ 
          success: boolean; 
          region: { id: number; name: string }; 
          is_new: boolean;
          message?: string 
        }>('/admin/regions', {
          name: addRegionForm.value.name.trim()
        })
        regionId = createRes.data.region.id
        extraMessage = createRes.data.message || ''
      }
      
      if (!regionId) {
        ElMessage.error('地区 ID 无效')
        return
      }
      
      await adminMoviesApi.addRegion(movieId, {
        region_id: regionId,
      })
      
      if (extraMessage) {
        ElMessage.success(extraMessage)
      } else {
        ElMessage.success('地区已添加')
      }
    addRegionVisible.value = false
    await loadDetail()
  } catch (e: any) { 
    ElMessage.error(e?.response?.data?.error || '添加失败') 
  }
  finally { addRegionSaving.value = false }
}

async function removeRegion(r: { id: number; name: string }) {
  try {
    await ElMessageBox.confirm(`确定移除地区「${r.name}」吗？`, '确认移除', { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await adminMoviesApi.removeRegion(movieId, r.id)
    if (detail.value) detail.value.regions = (detail.value.regions || []).filter(x => x.id !== r.id)
    ElMessage.success('已移除')
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '移除失败') }
}

/* ── 评分 ── */
function openEditRating() {
  editRatingForm.value = {
    average: detail.value?.rating?.average || 0,
    count: detail.value?.rating?.count || 0,
  }
  editRatingVisible.value = true
}

async function submitEditRating() {
  editRatingSaving.value = true
  try {
    const res = await adminMoviesApi.updateRating(movieId, editRatingForm.value)
    if (detail.value) {
      detail.value.rating = { ...detail.value.rating, average: res.data.average, count: res.data.count, distribution: detail.value.rating?.distribution }
    }
    ElMessage.success('评分已更新')
    editRatingVisible.value = false
  } catch (e: any) { ElMessage.error(e?.response?.data?.error || '保存失败') }
  finally { editRatingSaving.value = false }
}

onMounted(() => {
  if (!movieId) { router.replace('/admin/movies'); return }
  loadDetail()
})
</script>

<style scoped>
.admin-movie-detail { max-width: 900px; padding: 0 24px 32px; }
.detail-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding: 12px 0; border-bottom: 1px solid #ebeef5; }
.detail-hero { display: flex; gap: 32px; flex-wrap: wrap; }
.detail-poster { width: 200px; flex-shrink: 0; position: relative; border-radius: 6px; overflow: hidden; }
.detail-poster.clickable { cursor: pointer; }
.detail-poster.clickable:hover .poster-mask { opacity: 1; }
.poster-img { width: 200px; min-height: 280px; border-radius: 6px; background: #f0f0f0; }
.poster-placeholder { width: 200px; height: 280px; display: flex; align-items: center; justify-content: center; color: #ccc; background: linear-gradient(135deg, #e0e0e0, #f5f5f5); border-radius: 6px; }
.poster-mask { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.3s; font-size: 14px; gap: 8px; border-radius: 6px; }
.cropper-container { height: 500px; }
.upload-error { color: #f56c6c; font-size: 13px; padding: 8px 0 0 10px; }
.detail-info { flex: 1; min-width: 300px; }
.detail-title { font-size: 24px; color: #1a1a2e; margin: 0 0 12px; }
.detail-meta { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; font-size: 14px; flex-wrap: wrap; }
.meta-item { color: #606266; }
.rating-star { display: flex; align-items: center; gap: 3px; color: #e8a838; font-weight: 500; }
.rating-count { color: #aaa; font-weight: 400; font-size: 13px; }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; align-items: center; }
.genre-tag { background: #e8a838; border-color: #e8a838; color: #fff; }
.status-row { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
.detail-rating { min-width: 240px; }
.rating-big { display: flex; flex-direction: column; align-items: center; margin-bottom: 12px; }
.rating-score { font-size: 48px; font-weight: 700; color: #e8a838; line-height: 1; }
.rating-total { font-size: 13px; color: #909399; margin-top: 4px; }
.rating-bars { width: 100%; }
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.bar-label { font-size: 13px; color: #909399; width: 30px; text-align: right; }
.bar-row .el-progress { flex: 1; }
.section { margin-bottom: 20px; }
.section-title { font-size: 16px; font-weight: 600; color: #1a1a2e; margin: 0 0 10px; }
.person-list { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.person-item { background: #f0f2f5; padding: 4px 12px; border-radius: 4px; font-size: 14px; color: #303133; display: inline-flex; align-items: center; gap: 4px; }
.person-item-inline { background: #f0f2f5; padding: 2px 8px; border-radius: 4px; font-size: 14px; color: #303133; display: inline-flex; align-items: center; gap: 2px; margin-right: 4px; }
.delete-icon { cursor: pointer; color: #c0c4cc; font-size: 14px; vertical-align: middle; }
.delete-icon:hover { color: #f56c6c; }
.crew-group { margin-bottom: 8px; font-size: 14px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 0; }
.crew-role { color: #909399; margin-right: 8px; flex-shrink: 0; }
.crew-names { color: #303133; }
.related-section { border-radius: 8px; }
.related-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
.related-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #fafafa; border-radius: 6px; }
.related-label { font-size: 13px; color: #909399; }
.related-value { font-size: 14px; color: #303133; font-weight: 500; margin-right: auto; }
.not-found { padding: 60px 0; }

.ai-summary {
  line-height: 1.8;
  color: #606266;
  padding: 8px 0 12px 0;
  text-indent: 2em;
}
.ai-summary.empty,
.empty {
  color: #c0c4cc;
  text-align: center;
  text-indent: 0;
  padding: 32px 0;
  margin: 0;
}
</style>
