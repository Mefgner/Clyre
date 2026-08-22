<template>
  <div v-if="thinking">
    <v-btn
      class="text-none text-grey px-1"
      density="comfortable"
      size="small"
      variant="text"
      @click="expanded = !expanded"
    >
      <v-icon class="mr-1">{{ expanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
      {{ streaming ? 'Thinking…' : 'Thought process' }}
    </v-btn>
    <div v-if="expanded" class="text-body-2 font-weight-light text-grey thinking-text">
      {{ thinking }}
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'

  withDefaults(
    defineProps<{
      thinking: string | null
      streaming?: boolean
    }>(),
    {
      streaming: false,
    },
  )

  const expanded = ref(false)
</script>

<style scoped>
.thinking-text {
  white-space: pre-wrap;
}
</style>
