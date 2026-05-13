<template>
  <span :class="['badge', `badge-${status}`]">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: 'pending' | 'claimed' | 'resolved' }>()

const label = computed(() => {
  const m: Record<string, string> = { pending: '待处理', claimed: '已认领', resolved: '已解决' }
  return m[props.status] || props.status
})
</script>

<style scoped>
.badge { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; }
.badge-pending { background: #fef0e5; color: #e6a23c; }
.badge-claimed { background: #ecf5ff; color: #409eff; }
.badge-resolved { background: #f0f9eb; color: #67c23a; }
</style>
