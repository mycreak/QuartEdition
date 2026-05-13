<template>
  <div class="avatar-upload">
    <!-- 头像预览 -->
    <div class="avatar-preview" @click="handleSelectFile">
      <el-image
        v-if="previewUrl"
        :src="previewUrl"
        fit="cover"
        class="avatar-img"
      >
        <template #error>
          <div class="avatar-placeholder">
            <el-icon :size="40"><User /></el-icon>
          </div>
        </template>
      </el-image>
      <div v-else class="avatar-placeholder">
        <el-icon :size="40" v-if="!loading"><User /></el-icon>
        <el-icon v-else :size="40" class="is-rotating"><Loading /></el-icon>
      </div>
      <div class="avatar-mask">
        <el-icon :size="20"><Camera /></el-icon>
        <span>{{ loading ? '上传中' : '更换头像' }}</span>
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
      title="裁剪头像"
      width="500px"
      :close-on-click-modal="false"
      @close="resetCropper"
    >
      <div class="cropper-container">
        <vue-cropper
          ref="cropperRef"
          :img="originImageUrl"
          :output-type="'webp'"
          :output-quality="0.8"
          :auto-crop="true"
          :auto-crop-width="200"
          :auto-crop-height="200"
          :fixed="true"
          :fixed-number="[1,1]"
          :center-box="true"
          :info="true"
          :can-move="true"
          :can-zoom="true"
          :can-rotate="false"
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
import { User, Camera, Loading } from '@element-plus/icons-vue'
import VueCropper from 'vue-cropper'
import 'vue-cropper/dist/index.css'
import { uploadAvatar } from '@/api/profile'

const props = defineProps<{
  /** 当前头像URL */
  modelValue?: string
}>()

const emit = defineEmits<{
  /** 上传成功回调 */
  (e: 'update:modelValue', url: string): void
  /** 上传成功事件 */
  (e: 'success', url: string): void
  /** 上传失败事件 */
  (e: 'error', err: Error): void
}>()

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

  // 校验文件大小
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error('头像大小不能超过2MB')
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
        const file = new File([blob], 'avatar.webp', { type: 'image/webp' })
        
        // 上传到后端
        const res = await uploadAvatar(file)
        const avatarUrl = res.data.data.avatar_url
        
        // 回调
        emit('update:modelValue', avatarUrl)
        emit('success', avatarUrl)
        ElMessage.success('头像上传成功')
        
        // 关闭弹窗
        cropperVisible.value = false
      } catch (err: any) {
        ElMessage.error(err.response?.data?.message || '头像上传失败')
        emit('error', err)
      } finally {
        uploading.value = false
        loading.value = false
      }
    })
  } catch (err: any) {
    ElMessage.error('头像裁剪失败')
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
  height: 400px;
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
