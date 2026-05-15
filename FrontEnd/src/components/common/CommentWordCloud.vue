<template>
  <div class="comment-word-cloud relative">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container flex flex-col items-center justify-center py-12">
      <el-icon class="animate-spin text-4xl text-blue-500 mb-3" :size="40"><Loading /></el-icon>
      <p class="text-gray-500">词云生成中...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!words.length" class="empty-container flex flex-col items-center justify-center py-12 text-gray-500">
      <el-icon :size="40" class="mb-3"><InfoFilled /></el-icon>
      <p>暂无足够短评生成词云</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-container flex flex-col items-center justify-center py-12 text-gray-500">
      <el-icon :size="40" class="mb-3 text-red-500"><WarningFilled /></el-icon>
      <p>{{ error }}</p>
      <el-button type="primary" plain size="small" class="mt-3" @click="$emit('retry')">重新生成</el-button>
    </div>

    <!-- 词云渲染 -->
    <div v-else ref="cloudRef" class="cloud-container"></div>
  </div>
</template>


<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import 'echarts-wordcloud'
import { Loading, InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import type { WordCloudItem } from '@/types/movie'

const props = defineProps<{
  words: WordCloudItem[]
  loading?: boolean
  error?: string
}>()

const emit = defineEmits<{
  'word-click': [word: WordCloudItem]
  'retry': []
}>()

const cloudRef = ref<HTMLElement | null>(null)
let chartInstance: echarts.ECharts | null = null

// 初始化echarts实例
const initChart = () => {
  if (!cloudRef.value) return
  if (chartInstance) chartInstance.dispose()

  chartInstance = echarts.init(cloudRef.value)

  // 词云配置
  const option = {
    tooltip: {
      show: true,
      formatter: (params: any) => {
        return `${params.name}`
      }
    },
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      left: 'center',
      top: 'center',
      width: '100%',
      height: '100%',
      right: null,
      bottom: null,
      sizeRange: [12, 60], // 权重0-200映射到字体大小12-60px
      rotationRange: [-90, 90],
      rotationStep: 45,
      gridSize: 8,
      drawOutOfBound: false,
      layoutAnimation: true,
      textStyle: {
        fontFamily: 'sans-serif',
        fontWeight: 'bold',
        color: () => {
          // 随机配色
          const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899']
          return colors[Math.floor(Math.random() * colors.length)]
        }
      },
      emphasis: {
        focus: 'self',
        textStyle: {
          shadowBlur: 10,
          shadowColor: 'rgba(0,0,0,0.3)'
        }
      },
      data: props.words.map(item => ({
        name: item.text,
        value: item.weight
      }))
    }]
  }

  chartInstance.setOption(option)

  // 点击事件
  chartInstance.on('click', (params: any) => {
    const clickedWord = props.words.find(w => w.text === params.name)
    if (clickedWord) {
      emit('word-click', clickedWord)
    }
  })

  // 窗口 resize 响应
  window.addEventListener('resize', handleResize)
}

// 响应式调整
const handleResize = () => {
  chartInstance?.resize()
}

// 监听words变化重新渲染
watch(() => props.words, () => {
  if (props.words.length && !props.loading && !props.error) {
    nextTick(() => {
      initChart()
    })
  }
}, { deep: true })

onMounted(() => {
  if (props.words.length && !props.loading && !props.error) {
    initChart()
  }
})

onBeforeUnmount(() => {
  chartInstance?.dispose()
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.comment-word-cloud {
  width: 100%;
  min-height: 400px;
  border-radius: 8px;
  background: #fff;
  position: relative;
}

.loading-container,
.empty-container,
.error-container {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.cloud-container {
  width: 100%;
  height: 400px;
}
</style>
