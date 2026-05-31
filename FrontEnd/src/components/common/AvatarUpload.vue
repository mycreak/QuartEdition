<template>
  <div class="avatar-upload">
    <!-- 预览 -->
    <div
      class="avatar-preview"
      :class="{ 'is-cover': mode === 'cover' }"
      @click="handleSelectFile"
    >
      <el-image
        v-if="previewUrl"
        :src="previewUrl"
        fit="cover"
        class="avatar-img"
      >
        <template #error>
          <div class="avatar-placeholder">
            <el-icon :size="iconSize" v-if="mode === 'avatar'"><User /></el-icon>
            <el-icon :size="iconSize" v-else><Picture /></el-icon>
          </div>
        </template>
      </el-image>
      <div v-else class="avatar-placeholder">
        <el-icon :size="iconSize" v-if="!loading && mode === 'avatar'"><User /></el-icon>
        <el-icon :size="iconSize" v-else-if="!loading && mode === 'cover'"><Picture /></el-icon>
        <el-icon v-else :size="iconSize" class="is-rotating"><Loading /></el-icon>
      </div>
      <div class="avatar-mask">
        <el-icon :size="20"><Camera /></el-icon>
        <span>{{ loading ? '上传中' : mode === 'cover' ? '更换封面' : '更换头像' }}</span>
      </div>
    </div>

    <!-- 隐藏的原生文件选择器 -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      style="display: none"
      @change="handleFileChange"
    />

    <!-- 裁剪弹窗 -->
    <el-dialog
      v-model="cropperVisible"
      :title="mode === 'cover' ? '裁剪封面' : '裁剪头像'"
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
          :auto-crop-width="cropWidth"
          :auto-crop-height="cropHeight"
          :fixed="true"
          :fixed-number="fixedRatio"
          :center-box="true"
          :info="true"
          :can-move="true"
          :can-scale="true"
        />
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="cropperVisible = false">取消</el-button>
          <el-button type="primary" @click="handleConfirmCrop" :loading="uploading">
            确认并上传
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { User, Camera, Loading, Picture } from '@element-plus/icons-vue'
import { VueCropper } from 'vue-cropper/next'
import 'vue-cropper/next/dist/index.css'
import { uploadAvatar, uploadListCover } from '@/api/profile'

const props = defineProps<{
  /** 当前URL */
  modelValue?: string
  /** 模式：avatar-头像，cover-封面 */
  mode?: 'avatar' | 'cover'
}>()

const emit = defineEmits<{
  /** 上传成功回调 */
  (e: 'update:modelValue', url: string): void
  /** 上传成功事件 */
  (e: 'success', url: string): void
  /** 上传失败事件 */
  (e: 'error', err: Error): void
}>()

const mode = computed(() => props.mode || 'avatar')
const fixedRatio = computed(() => mode.value === 'cover' ? [4, 1] : [1, 1])
const cropWidth = computed(() => mode.value === 'cover' ? 1280 : 200)
const cropHeight = computed(() => mode.value === 'cover' ? 320 : 200)
const iconSize = computed(() => mode.value === 'avatar' ? 40 : 60)

const fileInputRef = ref<HTMLInputElement | null>(null)
const cropperRef = ref<InstanceType<typeof VueCropper> | null>(null)
const cropperVisible = ref(false)
const originImageUrl = ref('')
const previewUrl = computed(() => props.modelValue || '')
const loading = ref(false)
const uploading = ref(false)

/** 触发文件选择 */
const handleSelectFile = () => {
  if (loading.value || uploading.value) return
  fileInputRef.value?.click()
}

/** 处理文件选择 */
const handleFileChange = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return

  // 校验文件大小（与后端 AVATAR_MAX_SIZE_MB=2 保持一致）
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过2MB')
    resetFileInput()
    return
  }

  // 校验文件格式
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    ElMessage.error('仅支持png/jpg/webp格式的图片')
    resetFileInput()
    return
  }

  // 生成预览URL，打开裁剪弹窗
  originImageUrl.value = URL.createObjectURL(file)
  cropperVisible.value = true
  resetFileInput()
}

/** 确认裁剪并上传 */
const handleConfirmCrop = async () => {
  if (!cropperRef.value) return

  uploading.value = true
  loading.value = true

  try {
    // 获取裁剪后的Blob
    cropperRef.value.getCropBlob(async (blob: Blob) => {
      try {
        // 转成File对象
        const fileName = mode.value === 'avatar' ? 'avatar.webp' : 'cover.webp'
        const file = new File([blob], fileName, { type: 'image/webp' })
        
        // 上传到后端
        let avatarUrl: string
        if (mode.value === 'avatar') {
          const res = await uploadAvatar(file)
          avatarUrl = res.data.data.avatar_url
        } else {
          const res = await uploadListCover(file)
          avatarUrl = res.data.data.cover_url
        }
        
        // 回调
        emit('update:modelValue', avatarUrl)
        emit('success', avatarUrl)
        ElMessage.success(mode.value === 'avatar' ? '头像上传成功' : '封面上传成功')
        
        // 关闭弹窗
        cropperVisible.value = false
      } catch (err: any) {
        ElMessage.error(err.response?.data?.error || err.response?.data?.message || '上传失败')
        emit('error', err)
      } finally {
        uploading.value = false
        loading.value = false
      }
    })
  } catch (err: any) {
    ElMessage.error('裁剪失败')
    uploading.value = false
    loading.value = false
  }
}

/** 重置文件选择器 */
const resetFileInput = () => {
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

/** 重置裁剪器 */
const resetCropper = () => {
  if (originImageUrl.value) {
    URL.revokeObjectURL(originImageUrl.value)
    originImageUrl.value = ''
  }
  cropperRef.value = null
}
</script>

<style scoped>
.avatar-upload {
  display: inline-block;
}

.avatar-preview {
  position: relative;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid #eee;
  transition: all 0.3s;
}

.avatar-preview.is-cover {
  width: 400px;
  height: 100px;
  border-radius: 8px;
}

.avatar-preview:hover {
  border-color: #409eff;
}

.avatar-preview:hover .avatar-mask {
  opacity: 1;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}

.avatar-mask {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s;
  font-size: 12px;
  gap: 4px;
}

.cropper-container {
  height: 450px;
  padding: 10px;
}

.is-rotating {
  animation: rotating 1.5s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
