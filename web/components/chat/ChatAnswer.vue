<script setup lang="ts">
  defineProps<{ message: string }>()
</script>

<template>
  <div class="font-weight-light pa-1 mt-3 mb-4">
    <pretty-markdown :value="message" />
  </div>
</template>
