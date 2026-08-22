<script setup lang="ts">
  withDefaults(
    defineProps<{
      message: string
      thinking?: string | null
      streaming?: boolean
    }>(),
    {
      thinking: null,
      streaming: false,
    },
  )
</script>

<template>
  <div class="font-weight-light pa-1 mt-3 mb-4">
    <thinking-block :streaming="streaming" :thinking="thinking" />
    <pretty-markdown :value="message" />
  </div>
</template>
