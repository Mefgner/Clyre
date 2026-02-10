<script setup lang="ts">
  defineProps<{ message: string }>()
</script>

<template>
  <div class="d-flex justify-end w-100">
    <v-card
      class="mb-2 pa-2 px-3"
      color="secondary"
      outlined
      rounded="xl"
      variant="tonal"
    >
      {{ message }}
    </v-card>
  </div>
</template>
