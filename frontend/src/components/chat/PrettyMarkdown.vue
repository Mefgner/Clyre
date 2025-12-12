<script setup lang="ts">
  import { marked } from 'marked'
  import { computed } from 'vue'

  const props = defineProps<{ value: string }>()

  const rendered = computed(() => marked(props.value))
</script>

<template>
  <div :key="$route.fullPath" class="w-100 pretty-rendered" v-html="rendered" />
</template>
