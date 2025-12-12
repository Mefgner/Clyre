<script setup lang="ts">
  import { useThreadStore } from '@/stores/thread.ts'

  const model = defineModel<boolean>({ default: false })

  const emit = defineEmits<{
    'confirm': []
    'update:vModel': [isActive: boolean]
  }>()

  const threadStore = useThreadStore()

  function confirm () {
    emit('confirm')
    model.value = false
  }
</script>

<template>
  <v-dialog v-model="model" max-width="400">
    <v-card rounded="xl">
      <v-card-title class="text-h5 font-weight-bold mx-2 mt-3">Are you sure?</v-card-title>
      <v-card-text>
        Are you sure you want to delete "<strong>{{ threadStore.currentThread.title }}</strong>" chat? This action cannot be undone.
      </v-card-text>

      <v-card-actions class="justify-end ma-2">
        <v-btn color="primary" @click="model = false">Cancel</v-btn>
        <v-btn color="secondary" variant="tonal" @click="confirm">Delete</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
