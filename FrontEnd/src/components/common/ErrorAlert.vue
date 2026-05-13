<template>
  <el-alert
    v-if="message"
    :title="message"
    :type="type"
    :closable="closable"
    show-icon
    @close="$emit('close')"
  />
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  message: string
  type?: 'error' | 'warning' | 'info' | 'success'
  closable?: boolean
}>(), {
  type: 'error',
  closable: true,
})

defineEmits<{ close: [] }>()
</script>
