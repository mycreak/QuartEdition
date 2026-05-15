<template>
  <div class="poster-upload">
    <div class="poster-preview" @click="handleSelectFile">
      <el-image
        v-if="previewUrl"
        :src="previewUrl"
        fit="contain"
        class="poster-img"
      >
        <template #error>
          <div class="poster-placeholder">
            <el-icon :size="40"><PictureFilled /></el-icon>
          </div>
        </template>
      </el-image>
      <div v-else class="poster-placeholder">
        <el-icon :size="40"><PictureFilled /></el-icon>
      </div>
      <div class="poster-mask">
        <el-icon :size="20"><Upload /></el-icon>
        <span>{{ uploading ? '上传中' : '更换海报' }}</span>
      </div>
    </div>

    <input
      ref="fileInputRef"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      style="display: none"
      @change="handleFileChange"
    />

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
          :auto-crop-width="640"
          :auto-crop-height="360"
          :fixed="true"
          :fixed-number="[16,9]"
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { PictureFilled, Upload } from '@element-plus/icons-vue'
import { VueCropper } from 'vue-cropper/next'
import 'vue-cropper/next/dist/index.css'
import { adminMoviesApi } from '@/api/admin/movies'

const props = defineProps<{
  modelValue?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', url: string): void
  (e: 'success', url: string): void
  (e: 'error', err: Error): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)
const cropperRef = ref<InstanceType<typeof VueCropper> | null>(null)
const cropperVisible = ref(false)
const originImageUrl = ref('')
const previewUrl = computed(() => props.modelValue || '')
const uploading = ref(false)
const uploadError = ref('')

const handleSelectFile = () => {
  if (uploading.value) return
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
  if (!cropperRef.value) return

  uploading.value = true
  uploadError.value = ''

  try {
    cropperRef.value.getCropBlob(async (blob: Blob) => {
      try {
        const file = new File([blob], 'poster.webp', { type: 'image/webp' })
        const res = await adminMoviesApi.uploadPoster(file)
        const posterUrl = res.data.data.poster_url

        emit('update:modelValue', posterUrl)
        emit('success', posterUrl)
        ElMessage.success('海报上传成功')
        cropperVisible.value = false
      } catch (err: any) {
        const msg = err.response?.data?.error || '海报上传失败'
        uploadError.value = msg
        ElMessage.error(msg)
        emit('error', err)
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
</script>

<style scoped>
.poster-upload {
  display: inline-block;
  width: 100%;
}

.poster-preview {
  position: relative;
  width: 100%;
  min-height: 160px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  border: 2px dashed #dcdfe6;
  transition: all 0.3s;
  background: #fafafa;
}

.poster-preview:hover {
  border-color: #409eff;
}

.poster-preview:hover .poster-mask {
  opacity: 1;
}

.poster-img {
  width: 100%;
  min-height: 160px;
  display: block;
}

.poster-placeholder {
  width: 100%;
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  background: linear-gradient(135deg, #f5f7fa, #e4e7ed);
}

.poster-mask {
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
  font-size: 13px;
  gap: 6px;
}

.cropper-container {
  height: 360px;
}

.upload-error {
  color: #f56c6c;
  font-size: 13px;
  padding: 8px 0 0 10px;
}
</style>
