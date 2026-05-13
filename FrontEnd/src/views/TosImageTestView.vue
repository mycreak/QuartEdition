<template>
  <div class="tos-image-test">
    <h1>火山引擎 TOS 图片测试页</h1>
    <el-card class="card">
      <template #header>
        <div class="card-header">
          <span>图片展示区域</span>
        </div>
      </template>

      <!-- ========================================== -->
      <!-- 👇 在此处编辑你的 TOS 图片 URL 👇 -->
      <!-- ========================================== -->
      <div class="image-container">
        <img
          :src="TOS_IMAGE_URL"
          alt="TOS 测试图片"
          class="tos-image"
          @load="onImageLoad"
          @error="onImageError"
        />
      </div>

      <div class="status-section">
        <el-alert
          :title="status.title"
          :type="status.type"
          :description="status.description"
          :closable="false"
          show-icon
        />
      </div>

      <div class="url-section">
        <el-divider>当前 URL</el-divider>
        <el-input
          :model-value="TOS_IMAGE_URL"
          type="textarea"
          :rows="3"
          readonly
        />
      </div>

      <div class="info-section">
        <el-divider>使用说明</el-divider>
        <ul>
          <li>找到文件 <code>src/views/TosImageTestView.vue</code></li>
          <li>编辑第 <strong>37 行</strong> 左右的 <code>TOS_IMAGE_URL</code> 常量</li>
          <li>保存文件后 Vite 会自动刷新，可实时查看效果</li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'

// ===============================================
// 👇 编辑此处的 TOS 图片 URL 👇
// ===============================================
const TOS_IMAGE_URL = 'https://movie-poster.tos-cn-guangzhou.volces.com/covers/preview.jpg'
// ===============================================

const status = reactive({
  title: '等待加载...',
  type: 'info' as const,
  description: '图片正在加载中，请稍候...'
})

const onImageLoad = () => {
  status.title = '✅ 图片加载成功'
  status.type = 'success'
  status.description = '火山引擎 TOS 图片正常展示！'
}

const onImageError = () => {
  status.title = '❌ 图片加载失败'
  status.type = 'error'
  status.description = '请检查 URL 是否正确、是否配置了 CORS 跨域权限、图片是否存在'
}
</script>

<style scoped>
.tos-image-test {
  padding: 30px;
  max-width: 900px;
  margin: 0 auto;
}

.tos-image-test h1 {
  margin-bottom: 20px;
  color: #303133;
}

.card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.image-container {
  text-align: center;
  padding: 30px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 20px;
}

.tos-image {
  max-width: 100%;
  max-height: 500px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.status-section {
  margin-bottom: 20px;
}

.url-section, .info-section {
  margin-top: 20px;
}

.info-section ul {
  line-height: 2;
}

.info-section code {
  background: #f5f7fa;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
}
</style>
