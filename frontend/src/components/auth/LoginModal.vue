<script setup lang="ts">
  import { ref } from 'vue'

  const email = ref('')
  const password = ref('')
  const model = defineModel<boolean>({ default: false })

  const emit = defineEmits<{
    'login': [email: string, password: string]
    'switch-to-register': []
    'update:modelValue': [isActive: boolean]
  }>()
</script>

<template>
  <v-dialog v-model="model" persistent>
    <v-card elevation="12" max-width="400" rounded="xl">
      <v-card-title class="text-h5 font-weight-bold pa-4 ml-1">
        Login to Clyre
      </v-card-title>
      <v-card-text class="pa-4">
        <form @submit.prevent.stop>
          <v-text-field v-model="email" density="compact" variant="outlined">
            <template #label>
              Email
            </template>
          </v-text-field>

          <v-text-field
            v-model="password"
            density="compact"
            type="password"
            variant="outlined"
          >
            <template #label>
              Password
            </template>
          </v-text-field>
        </form>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0 justify-space-between">
        <v-btn color="primary" variant="text" @click="emit('switch-to-register')">
          Register instead
        </v-btn>
        <v-btn color="primary" variant="flat" @click="emit('login', email, password)">
          Login
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
