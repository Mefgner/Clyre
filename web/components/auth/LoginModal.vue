<script setup lang="ts">
  import { ref } from 'vue'

  const email = ref('')
  const password = ref('')
  const model = defineModel<boolean>({ default: false })

  defineProps<{ authError: string }>()

  const emit = defineEmits<{
    'login': [email: string, password: string]
    'switch-to-register': []
    'update:modelValue': [isActive: boolean]
  }>()
</script>

<template>
  <v-dialog v-model="model" max-width="400" persistent>
    <v-card elevation="12" rounded="xl">
      <v-card-title class="text-h5 font-weight-bold pa-4 pb-2 ml-2">
        Login to Clyre
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <form @submit.prevent.stop>
          <v-text-field
            v-model="email"
            autocomplete="email"
            class="mb-4"
            density="compact"
            label="Email"
            rounded="xl"
            variant="outlined"
          />

          <v-text-field
            v-model="password"
            autocomplete="current-password"
            class="mb-1"
            density="compact"
            label="Password"
            rounded="xl"
            type="password"
            variant="outlined"
          />
        </form>
        <span v-if="authError" class="ml-2 text-red-accent-1 text-caption">
          {{ authError }}
        </span>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0 justify-space-between">
        <v-btn color="primary" variant="text" @click="emit('switch-to-register')">
          Register instead
        </v-btn>
        <v-btn color="primary" :disabled="!password || !email" variant="flat" @click="emit('login', email, password)">
          Login
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
