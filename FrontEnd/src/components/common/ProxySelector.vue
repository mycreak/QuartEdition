<template>
  <el-select
    v-model="selectedKey"
    placeholder="选择代理"
    style="width: 100%"
    filterable
    :loading="loading"
    @change="handleChange"
  >
    <el-option
      label="不使用代理"
      value=""
    />
    <el-option
      v-for="proxy in proxyOptions"
      :key="proxy.id"
      :label="proxy.region ? `${proxy.label} (${proxy.region})` : proxy.label"
      :value="proxy.key"
    />
  </el-select>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { adminProxyApi, type ProxyOption } from '@/api/admin/infra'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const loading = ref(false)
const proxyOptions = ref<ProxyOption[]>([])
const selectedKey = ref('')

// 加载代理列表
const loadProxies = async () => {
  loading.value = true
  try {
    const res = await adminProxyApi.options()
    proxyOptions.value = res.data.items || []
  } catch {
    ElMessage.error('加载代理列表失败')
  } finally {
    loading.value = false
  }
}

// 选择变化
const handleChange = (value: string) => {
  emit('update:modelValue', value)
}

// 监听外部值变化
watch(() => props.modelValue, (value) => {
  selectedKey.value = value
}, { immediate: true })

onMounted(() => {
  loadProxies()
})
</script>

<style scoped>
</style>