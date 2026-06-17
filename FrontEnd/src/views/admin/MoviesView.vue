<template>
  <div class="admin-movies">
    <h2 class="page-title">电影管理</h2>

    <!-- 有管理权限显示tab -->
    <el-tabs v-model="activeTab" class="movie-tabs" v-if="authStore.checkPermission('movie:manage')">
      <!-- 电影列表tab -->
      <el-tab-pane label="电影列表" name="movies">
        <div class="toolbar">
          <el-input v-model="keyword" placeholder="搜索片名 / douban_id..." clearable class="search-input" />
          <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select" style="width: 140px">
            <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
          </el-select>
          <el-input v-model="yearFilter" placeholder="年份" clearable class="year-input" maxlength="4" @blur="onYearFilterChange" @keyup.enter="onYearFilterChange" />
          <el-select v-model="regionFilter" placeholder="全部国家/地区" clearable class="filter-select" style="width: 150px">
            <el-option v-for="r in allRegions" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
          <el-select v-model="ratingFilter" placeholder="全部评分" clearable class="filter-select" style="width: 130px">
            <el-option label="9分及以上" value="100:90" />
            <el-option label="8-9分" value="90:80" />
            <el-option label="7-8分" value="80:70" />
            <el-option label="6-7分" value="70:60" />
            <el-option label="6分以下" value="60:0" />
          </el-select>
          <el-select v-model="publishedFilter" placeholder="上下架" clearable class="filter-select">
            <el-option label="已上架" value="published" />
            <el-option label="已下架" value="unpublished" />
          </el-select>
        </div>

        <el-table :data="movies" stripe v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="douban_id" label="豆瓣ID" width="100" />
          <el-table-column prop="title" label="片名" min-width="200" />
          <el-table-column label="类型" min-width="140">
            <template #default="{ row }">
              <el-tag v-for="g in (row.genres || [])" :key="g" size="small" class="genre-tag">{{ g }}</el-tag>
              <span v-if="!row.genres?.length" class="c-gray">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="release_year" label="年份" width="80" />
          <el-table-column label="地区" min-width="140">
            <template #default="{ row }">
              <el-tag v-for="r in (row.regions || [])" :key="r.id" size="small" class="genre-tag">{{ r.name }}</el-tag>
              <span v-if="!row.regions?.length" class="c-gray">—</span>
            </template>
          </el-table-column>
          <el-table-column label="评分" width="100">
            <template #default="{ row }">
              <span class="rating-cell">{{ row.rating?.average?.toFixed(1) || '-' }}</span>
              <span class="rating-count" v-if="row.rating?.count">({{ row.rating.count }})</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_published ? 'success' : 'info'" size="small">{{ row.is_published ? '已上架' : '已下架' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
              <el-button v-if="authStore.checkPermission('movie:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="togglePublish(row)">
                {{ row.is_published ? '下架' : '上架' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination class="paginator" v-model:current-page="page" :total="total" :page-size="pageSize" background layout="total, prev, pager, next" @current-change="fetchList" />
      </el-tab-pane>

      <!-- 重名人员审核tab -->
      <el-tab-pane label="重名人员审核" name="duplicate">
        <div class="toolbar">
          <el-button type="primary" @click="refreshDuplicateList" :loading="duplicateLoading">刷新列表</el-button>
        </div>

        <el-table :data="duplicateList" stripe v-loading="duplicateLoading">
          <el-table-column prop="name" label="重名姓名" width="150" />
          <el-table-column label="人员1" min-width="200">
            <template #default="{ row }">
              <span>{{ row.person_name1 }} (ID: {{ row.person_id1 }})</span>
            </template>
          </el-table-column>
          <el-table-column label="人员2" min-width="200">
            <template #default="{ row }">
              <span>{{ row.person_name2 }} (ID: {{ row.person_id2 }})</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="发现时间" width="180" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDuplicateDetail(row)">查看关联电影</el-button>
              <el-button size="small" type="warning" link @click="openHandleDialog(row)">处理</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination class="paginator" v-model:current-page="duplicatePage" :total="duplicateTotal" :page-size="duplicatePageSize" background layout="total, prev, pager, next" @current-change="fetchDuplicateList" />
      </el-tab-pane>

      <!-- 标签审核 tab -->
      <el-tab-pane label="标签审核" name="styleTags">
        <div class="toolbar">
          <el-button type="primary" @click="fetchStyleTags" :loading="styleTagLoading">刷新列表</el-button>
        </div>

        <el-table :data="styleTagItems" stripe v-loading="styleTagLoading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column label="待合并标签" min-width="140">
            <template #default="{ row }">
              <el-tag size="small" type="warning">{{ row.name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="合并到" min-width="140">
            <template #default="{ row }">
              <el-tag size="small" type="success">{{ row.merged_to_tag_name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="维度" width="80">
            <template #default="{ row }">{{ row.dimension || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="success" link :loading="styleTagLoadingId === row.id" @click="handleStyleTagMerge(row)">确认合并</el-button>
              <el-button size="small" type="warning" link :loading="styleTagLoadingId === row.id" @click="handleStyleTagReject(row)">拒绝</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!styleTagLoading && !styleTagItems.length" style="text-align:center;color:#c0c4cc;padding:32px">暂无待审核标签</div>

        <el-pagination
          v-if="styleTagTotal > styleTagPageSize"
          class="paginator"
          v-model:current-page="styleTagPage"
          :total="styleTagTotal"
          :page-size="styleTagPageSize"
          background
          layout="total, prev, pager, next"
          @current-change="fetchStyleTags"
        />
      </el-tab-pane>

      <!-- 片单管理 tab -->
      <el-tab-pane label="片单管理" name="playlists">
        <div class="toolbar">
          <el-input v-model="playlistSearch" placeholder="搜索片单标题..." clearable class="search-input" @keyup.enter="fetchPlaylists" @blur="fetchPlaylists" @clear="fetchPlaylists" />
          <el-select v-model="playlistPublishedFilter" placeholder="上下架" clearable class="filter-select" @change="fetchPlaylists">
            <el-option label="已上架" :value="1" />
            <el-option label="未上架" :value="0" />
          </el-select>
          <el-date-picker
            v-model="playlistDateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="上架开始"
            end-placeholder="上架结束"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DDTHH:mm:ss"
            @change="fetchPlaylists"
          />
          <el-button type="primary" @click="openPlaylistCreate">新建片单</el-button>
        </div>

        <el-table :data="pagedPlaylistItems" stripe v-loading="playlistLoading">
          <el-table-column prop="id" label="ID" width="60" />
          <el-table-column prop="title" label="标题" min-width="160" />
          <el-table-column label="封面" width="80">
            <template #default="{ row }">
              <el-image v-if="row.cover_url" :src="row.cover_url" fit="cover" style="width:48px;height:32px;border-radius:4px" />
              <span v-else class="c-gray">—</span>
            </template>
          </el-table-column>
          <el-table-column label="影片数" width="80">
            <template #default="{ row }">{{ row.movie_ids?.length || 0 }}部</template>
          </el-table-column>
          <el-table-column prop="sort_order" label="排序" width="70" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_published ? 'success' : 'info'" size="small">
                {{ row.is_published ? '已上架' : '未上架' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="160">
            <template #default="{ row }">
              <div class="time-cell">
                <span v-if="row.publish_at" class="time-line">上架 {{ formatDateShort(row.publish_at) }}</span>
                <span v-if="row.unpublish_at" class="time-line">下架 {{ formatDateShort(row.unpublish_at) }}</span>
                <span v-if="!row.publish_at && !row.unpublish_at" class="c-gray">—</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="openPlaylistEdit(row)">编辑</el-button>
              <el-button v-if="!row.is_published" size="small" type="success" link @click="handlePlaylistPublish(row)">上架</el-button>
              <el-button v-else size="small" type="warning" link @click="handlePlaylistUnpublish(row)">下架</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          class="paginator"
          v-model:current-page="playlistPage"
          :total="playlistTotal"
          :page-size="playlistPageSize"
          background
          layout="total, prev, pager, next"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 无管理权限直接显示电影列表 -->
    <template v-else>
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索片名 / douban_id..." clearable class="search-input" />
        <el-select v-model="typeFilter" placeholder="全部类型" clearable class="filter-select" style="width: 140px">
          <el-option v-for="t in typeOptions" :key="t.type_num" :label="`${t.type_name} (${t.type_num})`" :value="t.type_num" />
        </el-select>
        <el-input v-model="yearFilter" placeholder="年份" clearable class="year-input" maxlength="4" />
        <el-select v-model="regionFilter" placeholder="全部国家/地区" clearable class="filter-select" style="width: 150px">
          <el-option v-for="r in allRegions" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
        <el-select v-model="ratingFilter" placeholder="全部评分" clearable class="filter-select" style="width: 130px">
          <el-option label="9分及以上" value="100:90" />
          <el-option label="8-9分" value="90:80" />
          <el-option label="7-8分" value="80:70" />
          <el-option label="6-7分" value="70:60" />
          <el-option label="6分以下" value="60:0" />
        </el-select>
        <el-select v-model="publishedFilter" placeholder="上下架" clearable class="filter-select">
          <el-option label="已上架" value="published" />
          <el-option label="已下架" value="unpublished" />
        </el-select>
      </div>

      <el-table :data="movies" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="douban_id" label="豆瓣ID" width="100" />
        <el-table-column prop="title" label="片名" min-width="200" />
        <el-table-column label="类型" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="g in (row.genres || [])" :key="g" size="small" class="genre-tag">{{ g }}</el-tag>
            <span v-if="!row.genres?.length" class="c-gray">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="release_year" label="年份" width="80" />
        <el-table-column label="地区" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="r in (row.regions || [])" :key="r.id" size="small" class="genre-tag">{{ r.name }}</el-tag>
            <span v-if="!row.regions?.length" class="c-gray">—</span>
          </template>
        </el-table-column>
        <el-table-column label="评分" width="100">
          <template #default="{ row }">
            <span class="rating-cell">{{ row.rating?.average?.toFixed(1) || '-' }}</span>
            <span class="rating-count" v-if="row.rating?.count">({{ row.rating.count }})</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_published ? 'success' : 'info'" size="small">{{ row.is_published ? '已上架' : '已下架' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
            <el-button v-if="authStore.checkPermission('movie:manage')" size="small" :type="row.is_published ? 'danger' : 'success'" link @click="togglePublish(row)">
              {{ row.is_published ? '下架' : '上架' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination class="paginator" v-model:current-page="page" :total="total" :page-size="pageSize" background layout="total, prev, pager, next" @current-change="fetchList" />
    </template>

    <!-- 重名人员详情弹窗 -->
    <el-dialog v-model="detailVisible" title="重名人员关联电影对比" width="1200px" destroy-on-close>
      <el-row :gutter="20">
        <el-col :span="12">
          <h4 style="margin-bottom: 12px;">
            人员：{{ currentDuplicate?.person_name1 }} (ID: {{ currentDuplicate?.person_id1 }})
            <span style="color: #909399; font-size: 14px; margin-left: 10px;">共 {{ person1Movies.length }} 部电影</span>
          </h4>
          <el-table :data="person1Movies" stripe v-loading="person1Loading" height="400">
            <el-table-column prop="title" label="电影名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="year" label="年份" width="80" />
            <el-table-column label="地区" min-width="150">
              <template #default="{ row }">
                <el-tag v-for="r in row.regions" :key="r" size="small" style="margin-bottom: 2px;">{{ r }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="role_type" label="角色" width="100" />
          </el-table>
        </el-col>
        <el-col :span="12">
          <h4 style="margin-bottom: 12px;">
            人员：{{ currentDuplicate?.person_name2 }} (ID: {{ currentDuplicate?.person_id2 }})
            <span style="color: #909399; font-size: 14px; margin-left: 10px;">共 {{ person2Movies.length }} 部电影</span>
          </h4>
          <el-table :data="person2Movies" stripe v-loading="person2Loading" height="400">
            <el-table-column prop="title" label="电影名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="year" label="年份" width="80" />
            <el-table-column label="地区" min-width="150">
              <template #default="{ row }">
                <el-tag v-for="r in row.regions" :key="r" size="small" style="margin-bottom: 2px;">{{ r }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="role_type" label="角色" width="100" />
          </el-table>
        </el-col>
      </el-row>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="warning" @click="openHandleDialog(currentDuplicate)">去处理</el-button>
      </template>
    </el-dialog>

    <!-- 重名处理弹窗 -->
    <el-dialog v-model="handleVisible" title="处理重名人员" width="600px" destroy-on-close>
      <div style="padding: 20px 0;">
        <p>待处理重名：<strong>{{ currentDuplicate?.name }}</strong></p>
        <p>人员A：{{ currentDuplicate?.person_name1 }} (ID: {{ currentDuplicate?.person_id1 }})</p>
        <p>人员B：{{ currentDuplicate?.person_name2 }} (ID: {{ currentDuplicate?.person_id2 }})</p>
        <el-divider />
        <p style="color: #606266;">请判断两人是否为同一人：</p>
      </div>
      <template #footer>
        <el-button @click="handleVisible = false">取消</el-button>
        <el-button type="info" @click="confirmNotSame" :loading="confirmLoading">不是同一人</el-button>
        <el-button type="primary" @click="openMergeDialog">合并为同一人</el-button>
      </template>
    </el-dialog>

    <!-- 合并人员确认弹窗 -->
    <el-dialog v-model="mergeVisible" title="确认合并人员" width="550px" destroy-on-close>
      <p style="margin-bottom: 20px;">合并后，废弃人员的所有电影关联将迁移到保留人员，废弃人员将被标记为无效，操作不可逆，请谨慎选择：</p>
      <el-radio-group v-model="keepPersonId" style="margin: 20px 0; padding-left: 20px;">
        <el-radio :label="currentDuplicate?.person_id1" style="margin-bottom: 10px;">
          保留：<strong>{{ currentDuplicate?.person_name1 }}</strong> (ID: {{ currentDuplicate?.person_id1 }})
          <span style="color: #909399; font-size: 12px; margin-left: 10px;">（废弃：{{ currentDuplicate?.person_name2 }}）</span>
        </el-radio>
        <el-radio :label="currentDuplicate?.person_id2">
          保留：<strong>{{ currentDuplicate?.person_name2 }}</strong> (ID: {{ currentDuplicate?.person_id2 }})
          <span style="color: #909399; font-size: 12px; margin-left: 10px;">（废弃：{{ currentDuplicate?.person_name1 }}）</span>
        </el-radio>
      </el-radio-group>
      <p style="color: #f56c6c; margin-top: 20px; padding: 10px; background: #fef0f0; border-radius: 4px;">⚠️ 警告：合并操作无法撤销，请确认选择正确！</p>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitMerge" :loading="mergeLoading" :disabled="keepPersonId === null">确认合并</el-button>
      </template>
    </el-dialog>

    <!-- 片单编辑弹窗 -->
    <el-dialog v-model="playlistDialogVisible" :title="playlistEditId ? '编辑片单' : '新建片单'" width="700px" destroy-on-close @closed="resetPlaylistForm">
      <el-form :model="playlistForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="playlistForm.title" placeholder="片单标题" maxlength="128" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="playlistForm.description" type="textarea" :rows="3" placeholder="推荐语/介绍文字（可选）" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="封面URL">
          <el-input v-model="playlistForm.cover_url" placeholder="封面图片链接（TOS 上传，可选）" />
        </el-form-item>

        <el-form-item label="影片列表" required>
          <div class="playlist-movie-ids">
            <el-tag
              v-for="(mid, idx) in playlistForm.movie_ids"
              :key="idx"
              closable
              size="default"
              class="movie-id-tag"
              @close="removeMovieId(idx)"
            >
              <span class="tag-idx">{{ idx + 1 }}.</span>
              {{ mid }}
            </el-tag>
            <el-input
              v-model="newMovieIdInput"
              placeholder="输入电影ID回车添加"
              size="small"
              style="width: 160px"
              @keyup.enter="addMovieId"
            />
          </div>
          <span class="form-hint" v-if="!playlistForm.movie_ids.length">至少添加1部电影</span>
        </el-form-item>

        <el-form-item label="排序">
          <el-input-number v-model="playlistForm.sort_order" :min="0" :max="99" />
          <span class="form-hint" style="margin-left:8px">越小越靠前</span>
        </el-form-item>

        <el-form-item label="定时上架">
          <el-date-picker
            v-model="playlistForm.publish_at"
            type="datetime"
            placeholder="上架时间（可选，留空=手动上架）"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
        <el-form-item label="定时下架">
          <el-date-picker
            v-model="playlistForm.unpublish_at"
            type="datetime"
            placeholder="下架时间（可选，留空=永不下架）"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="playlistDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="playlistSaving" @click="savePlaylist">
          {{ playlistEditId ? '保存修改' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminMoviesApi } from '@/api/admin/movies'
import { adminPlaylistApi, type PlaylistFull } from '@/api/admin/playlists'
import client from '@/api/client'
import type { Movie } from '@/types/movie'

const router = useRouter()
const authStore = useAuthStore()
const movies = ref<Movie[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const typeFilter = ref<number | undefined>(undefined)
const yearFilter = ref('')
const regionFilter = ref<number | undefined>(undefined)
const publishedFilter = ref('')
const ratingFilter = ref('')
const allRegions = ref<{ id: number; name: string }[]>([])

// 重名人员管理相关变量
const activeTab = ref('movies')
const duplicateList = ref<{ id: number; name: string; person_id1: number; person_name1: string; person_id2: number; person_name2: string; created_at: string }[]>([])
const duplicateTotal = ref(0)
const duplicatePage = ref(1)
const duplicatePageSize = ref(20)
const duplicateLoading = ref(false)

// 弹窗相关变量
const detailVisible = ref(false)
const handleVisible = ref(false)
const mergeVisible = ref(false)
const currentDuplicate = ref<{ id: number; name: string; person_id1: number; person_name1: string; person_id2: number; person_name2: string } | null>(null)
const person1Movies = ref<{ movie_id: number; title: string; poster: string; year: number; regions: string[]; role_type: string }[]>([])
const person2Movies = ref<{ movie_id: number; title: string; poster: string; year: number; regions: string[]; role_type: string }[]>([])
const person1Loading = ref(false)
const person2Loading = ref(false)
const confirmLoading = ref(false)
const mergeLoading = ref(false)
const keepPersonId = ref<number | null>(null)

const TYPE_MAP: Record<number, string> = {
  1: '纪录片', 2: '传记', 3: '犯罪', 4: '历史', 5: '动作',
  6: '情色', 7: '歌舞', 8: '儿童', 10: '悬疑', 11: '剧情',
  12: '灾难', 13: '爱情', 14: '音乐', 15: '冒险', 16: '奇幻',
  17: '科幻', 18: '运动', 19: '惊悚', 20: '恐怖', 22: '战争',
  23: '短片', 24: '喜剧', 25: '动画', 27: '西部', 28: '家庭',
  29: '武侠', 30: '古装', 31: '黑色电影',
}

const typeOptions = Object.entries(TYPE_MAP).map(
  ([num, name]) => ({ type_num: Number(num), type_name: name })
)

let timer: ReturnType<typeof setTimeout> | null = null

async function fetchAllRegions() {
  try {
    const res = await client.get<{ id: number; name: string }[]>('/admin/regions')
    allRegions.value = res.data || []
  } catch {
    ElMessage.error('加载地区列表失败')
  }
}

async function fetchList(p = 1) {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: p, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (typeFilter.value) params.type_num = typeFilter.value
    if (yearFilter.value) {
      const y = parseInt(yearFilter.value, 10)
      if (!isNaN(y)) params.release_year = y
    }
    if (regionFilter.value !== undefined) params.region_id = regionFilter.value
    if (publishedFilter.value === 'published') params.published = 1
    else if (publishedFilter.value === 'unpublished') params.published = 0
    if (ratingFilter.value) params.interval_ids = ratingFilter.value
    const res = await adminMoviesApi.list(params as any)
    movies.value = res.data.items
    total.value = res.data.total
    page.value = p
  } catch { /* ignore */ } finally { loading.value = false }
}

function viewDetail(row: Movie) {
  router.push(`/admin/movies/${row.id}`)
}

async function togglePublish(row: Movie) {
  try {
    const api = row.is_published ? adminMoviesApi.unpublish : adminMoviesApi.publish
    await api(row.id)
    row.is_published = !row.is_published
    ElMessage.success(row.is_published ? '已上架' : '已下架')
  } catch { ElMessage.error('操作失败') }
}

// ==================== 重名人员管理相关方法 ====================
async function fetchDuplicateList(p = 1) {
  duplicateLoading.value = true
  try {
    const res = await client.get<{ items: any[]; total: number }>('/admin/duplicate-persons', {
      params: { page: p, page_size: duplicatePageSize.value }
    })
    duplicateList.value = res.data.items
    duplicateTotal.value = res.data.total
    duplicatePage.value = p
  } catch {
    ElMessage.error('加载重名列表失败')
  } finally {
    duplicateLoading.value = false
  }
}

function refreshDuplicateList() {
  fetchDuplicateList(1)
}

async function viewDuplicateDetail(row: any) {
  currentDuplicate.value = row
  detailVisible.value = true
  person1Loading.value = true
  person2Loading.value = true
  
  try {
    // 并行请求两个人的关联电影
    const [res1, res2] = await Promise.all([
      client.get<{ items: any[] }>(`/admin/duplicate-persons/${row.person_id1}/movies`),
      client.get<{ items: any[] }>(`/admin/duplicate-persons/${row.person_id2}/movies`)
    ])
    person1Movies.value = res1.data.items
    person2Movies.value = res2.data.items
  } catch {
    ElMessage.error('加载人员关联电影失败')
  } finally {
    person1Loading.value = false
    person2Loading.value = false
  }
}

function openHandleDialog(row: any) {
  currentDuplicate.value = row
  handleVisible.value = true
}

async function confirmNotSame() {
  if (!currentDuplicate.value) return
  // 二次确认
  try {
    await ElMessageBox.confirm(
      `确认【${currentDuplicate.value.person_name1}】和【${currentDuplicate.value.person_name2}】不是同一人吗？确认后两人将被标记为正常，不再出现在重名列表中。`,
      '确认处理',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  confirmLoading.value = true
  try {
    await client.post('/admin/duplicate-persons/confirm-not-same', {
      duplicate_id: currentDuplicate.value.id,
      person_id1: currentDuplicate.value.person_id1,
      person_id2: currentDuplicate.value.person_id2
    })
    ElMessage.success('处理成功')
    handleVisible.value = false
    fetchDuplicateList() // 刷新列表
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '处理失败，请稍后重试')
  } finally {
    confirmLoading.value = false
  }
}

function openMergeDialog() {
  keepPersonId.value = null
  mergeVisible.value = true
}

async function submitMerge() {
  if (!currentDuplicate.value || keepPersonId.value === null) {
    ElMessage.warning('请选择要保留的人员')
    return
  }
  // 计算要废弃的人员ID
  const discardPersonId = keepPersonId.value === currentDuplicate.value.person_id1 
    ? currentDuplicate.value.person_id2 
    : currentDuplicate.value.person_id1
  const keepName = keepPersonId.value === currentDuplicate.value.person_id1 ? currentDuplicate.value.person_name1 : currentDuplicate.value.person_name2
  const discardName = keepPersonId.value === currentDuplicate.value.person_id1 ? currentDuplicate.value.person_name2 : currentDuplicate.value.person_name1

  // 二次确认
  try {
    await ElMessageBox.confirm(
      `确认合并吗？合并后【${discardName}】将被标记为无效，所有关联的电影都会迁移到【${keepName}】，操作不可逆！`,
      '确认合并',
      { type: 'warning', confirmButtonText: '确认合并', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  mergeLoading.value = true
  try {
    await client.post('/admin/duplicate-persons/merge', {
      duplicate_id: currentDuplicate.value.id,
      keep_person_id: keepPersonId.value,
      discard_person_id: discardPersonId
    })
    ElMessage.success('合并成功')
    mergeVisible.value = false
    handleVisible.value = false
    fetchDuplicateList() // 刷新列表
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '合并失败，请稍后重试')
  } finally {
    mergeLoading.value = false
  }
}

function formatDateShort(iso: string): string {
  if (!iso) return ''
  return iso.replace('T', ' ').slice(0, 16)
}

// ==================== 标签审核方法 ====================
interface StyleTagItem {
  id: number
  name: string
  merged_to_tag_name: string
  dimension: string | null
}

const styleTagItems = ref<StyleTagItem[]>([])
const styleTagTotal = ref(0)
const styleTagPage = ref(1)
const styleTagPageSize = ref(20)
const styleTagLoading = ref(false)
const styleTagLoadingId = ref<number | null>(null)

async function fetchStyleTags(p = 1) {
  styleTagLoading.value = true
  styleTagPage.value = p
  try {
    const res = await client.get<{ items: StyleTagItem[]; total: number }>('/admin/style-tags/pending', {
      params: { page: p, page_size: styleTagPageSize.value }
    })
    styleTagItems.value = res.data.items
    styleTagTotal.value = res.data.total
  } catch {
    ElMessage.error('加载待审核标签失败')
  } finally {
    styleTagLoading.value = false
  }
}

async function handleStyleTagMerge(row: StyleTagItem) {
  try {
    await ElMessageBox.confirm(`确认将「${row.name}」合并到「${row.merged_to_tag_name}」吗？`, '确认合并', { type: 'warning' })
  } catch { return }

  styleTagLoadingId.value = row.id
  try {
    await client.post(`/admin/style-tags/${row.id}/confirm-merge`)
    ElMessage.success('已合并')
    fetchStyleTags(styleTagPage.value)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.error || '合并失败')
  } finally {
    styleTagLoadingId.value = null
  }
}

async function handleStyleTagReject(row: StyleTagItem) {
  try {
    await ElMessageBox.confirm(`确认拒绝「${row.name}」合并到「${row.merged_to_tag_name}」吗？`, '确认拒绝', { type: 'warning' })
  } catch { return }

  styleTagLoadingId.value = row.id
  try {
    await client.post(`/admin/style-tags/${row.id}/reject-merge`)
    ElMessage.success('已拒绝')
    fetchStyleTags(styleTagPage.value)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.error || '操作失败')
  } finally {
    styleTagLoadingId.value = null
  }
}

// ==================== 片单管理方法 ====================
const playlistItems = ref<PlaylistFull[]>([])
const playlistLoading = ref(false)
const playlistPublishedFilter = ref<number | undefined>(undefined)
const playlistSearch = ref('')
const playlistDateRange = ref<[string, string] | null>(null)
const playlistPage = ref(1)
const playlistPageSize = ref(20)

const playlistTotal = computed(() => playlistItems.value.length)
const pagedPlaylistItems = computed(() => {
  const start = (playlistPage.value - 1) * playlistPageSize.value
  return playlistItems.value.slice(start, start + playlistPageSize.value)
})
const playlistDialogVisible = ref(false)
const playlistEditId = ref<number | null>(null)
const playlistSaving = ref(false)
const newMovieIdInput = ref('')

const playlistForm = reactive({
  title: '',
  description: '',
  cover_url: '',
  movie_ids: [] as number[],
  sort_order: 0,
  publish_at: null as string | null,
  unpublish_at: null as string | null,
})

function resetPlaylistForm() {
  playlistForm.title = ''
  playlistForm.description = ''
  playlistForm.cover_url = ''
  playlistForm.movie_ids = []
  playlistForm.sort_order = 0
  playlistForm.publish_at = null
  playlistForm.unpublish_at = null
  playlistEditId.value = null
  newMovieIdInput.value = ''
}

function addMovieId() {
  const val = parseInt(newMovieIdInput.value.trim(), 10)
  if (!isNaN(val) && val > 0 && !playlistForm.movie_ids.includes(val)) {
    playlistForm.movie_ids.push(val)
  }
  newMovieIdInput.value = ''
}

function removeMovieId(idx: number) {
  playlistForm.movie_ids.splice(idx, 1)
}

async function fetchPlaylists() {
  playlistLoading.value = true
  playlistPage.value = 1
  try {
    const res = await adminPlaylistApi.list({
      keyword: playlistSearch.value || undefined,
      is_published: playlistPublishedFilter.value,
      publish_after: playlistDateRange.value?.[0] || undefined,
      publish_before: playlistDateRange.value?.[1] || undefined,
    })
    playlistItems.value = res.data.items
  } catch {
    ElMessage.error('加载片单列表失败')
  } finally {
    playlistLoading.value = false
  }
}

function openPlaylistCreate() {
  router.push('/admin/playlists/new')
}

function openPlaylistEdit(row: PlaylistFull) {
  router.push(`/admin/playlists/${row.id}/edit`)
}

async function savePlaylist() {
  if (!playlistForm.title.trim()) { ElMessage.warning('请输入标题'); return }
  if (!playlistForm.movie_ids.length) { ElMessage.warning('请至少添加1部电影'); return }

  playlistSaving.value = true
  try {
    const body: any = {
      title: playlistForm.title.trim(),
      movie_ids: playlistForm.movie_ids,
      description: playlistForm.description.trim(),
      cover_url: playlistForm.cover_url.trim(),
      sort_order: playlistForm.sort_order,
      publish_at: playlistForm.publish_at || null,
      unpublish_at: playlistForm.unpublish_at || null,
    }
    if (playlistEditId.value) {
      await adminPlaylistApi.update(playlistEditId.value, body)
      ElMessage.success('保存成功')
    } else {
      await adminPlaylistApi.create(body)
      ElMessage.success('创建成功')
    }
    playlistDialogVisible.value = false
    fetchPlaylists()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.error || '操作失败')
  } finally {
    playlistSaving.value = false
  }
}

async function handlePlaylistPublish(row: PlaylistFull) {
  try {
    await adminPlaylistApi.publish(row.id)
    row.is_published = 1
    ElMessage.success('已上架')
  } catch { ElMessage.error('上架失败') }
}

async function handlePlaylistUnpublish(row: PlaylistFull) {
  try {
    await adminPlaylistApi.unpublish(row.id)
    row.is_published = 0
    ElMessage.success('已下架')
  } catch { ElMessage.error('下架失败') }
}

async function handlePlaylistDelete(row: PlaylistFull) {
  try {
    await ElMessageBox.confirm(`确认删除片单「${row.title}」吗？删除不可恢复。`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await adminPlaylistApi.delete(row.id)
    ElMessage.success('已删除')
    fetchPlaylists()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.error || '删除失败')
  }
}

watch(keyword, () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => fetchList(1), 300)
})

// 监听tab切换，切换到重名审核时加载列表
watch(activeTab, (newVal) => {
  if (newVal === 'duplicate' && duplicateList.value.length === 0) {
    fetchDuplicateList()
  }
  if (newVal === 'styleTags' && styleTagItems.value.length === 0) {
    fetchStyleTags()
  }
  if (newVal === 'playlists' && playlistItems.value.length === 0) {
    fetchPlaylists()
  }
})

watch(typeFilter, () => fetchList(1))
// 年份筛选失焦/回车时触发查询
function onYearFilterChange() {
  fetchList(1)
}
watch(regionFilter, () => fetchList(1))
watch(publishedFilter, () => fetchList(1))
watch(ratingFilter, () => fetchList(1))

onMounted(async () => {
  await fetchAllRegions()
  fetchList()
})
</script>

<style scoped>
.admin-movies { max-width: 1280px; }
.page-title { font-size: 22px; color: #1a1a2e; margin: 0 0 20px; }
.movie-tabs { margin-bottom: 20px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.search-input { width: 280px; }
.filter-select { width: 120px; }
.year-input { width: 100px; }
.rating-cell { color: #e8a838; font-weight: 600; }
.rating-count { font-size: 11px; color: #aaa; }
.genre-tag { margin-right: 4px; margin-bottom: 2px; }
.c-gray { color: #c0c4cc; }
.paginator { margin-top: 16px; justify-content: flex-end; }

/* 片单管理 */
.playlist-movie-ids {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.movie-id-tag {
  font-size: 13px;
}
.tag-idx {
  color: #409eff;
  font-weight: 600;
  margin-right: 4px;
}
.form-hint {
  font-size: 12px;
  color: #909399;
}
.time-cell {
  font-size: 12px;
  color: #606266;
}
.time-line {
  display: block;
  line-height: 1.5;
}
</style>
