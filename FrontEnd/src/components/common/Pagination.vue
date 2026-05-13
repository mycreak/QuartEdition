<template>
  <div v-if="total > 0" class="pagination-wrapper">
    <el-pagination
      :current-page="current"
      :page-size="pageSize"
      :total="total"
      :page-sizes="[12, 24, 48]"
      layout="total, sizes, prev, pager, next, jumper"
      :background="true"
      @current-change="$emit('change', $event)"
      @size-change="$emit('sizeChange', $event)"
    />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  current: number
  total: number
  pageSize: number
}>()

defineEmits<{
  change: [page: number]
  sizeChange: [size: number]
}>()
</script>

<style scoped>
.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}
</style>
