<template>
  <el-select
    v-model="selectedValue"
    placeholder="选择Cookie"
    style="width: 100%"
    filterable
    :loading="loading"
    @change="handleChange"
  >
    <el-option
      label="不使用Cookie"
      value=""
    />
    <el-option
      v-for="option in options"
      :key="option.id"
      :label="`${option.label || option.id} (${option.platform}) [${option.allowed_regions.join(',')}]`"
      :value="option.id"
    />
  </el-select>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { adminCookieApi, type CookieOption } from '@/api/admin/infra'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const loading = ref(false)
const options = ref<CookieOption[]>([])
const selectedValue = ref('')

// 加载Cookie列表
const loadOptions = async () => {
  loading.value = true
  try {
    const res = await adminCookieApi.options()
    options.value = res.data.items || []
  } catch {
    ElMessage.error('加载Cookie列表失败')
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
  selectedValue.value = value
}, { immediate: true })

onMounted(() => {
  loadOptions()
})
</script>

<style scoped>
</style>
">