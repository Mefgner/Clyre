<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { validateRegisterCredentials } from '@/utils/validation.ts'

  const email = ref('')
  const password = ref('')
  const name = ref('')
  const passwordCopy = ref('')

  const error = computed(() => validateRegisterCredentials(name.value, email.value, password.value, passwordCopy.value))

  defineProps<{ authError: string }>()

  const model = defineModel<boolean>({ default: false })

  const emit = defineEmits<{
    'register': [email: string, password: string, name: string]
    'switch-to-login': []
    'update:vModel': [isActive: boolean]
  }>()
</script>

<template>
  <v-dialog v-model="model" max-width="400" persistent>
    <v-card elevation="12" rounded="xl">
      <v-card-title class="text-h5 font-weight-bold pa-4 pb-2 ml-2">
        Register for Clyre
      </v-card-title>
      <v-card-text class="mb-1 pb-1">
        <form class="d-flex flex-column ga-3 mb-2" @submit.prevent.stop>
          <v-text-field
            v-model="name"
            density="comfortable"
            label="Username"
            rounded="xl"
            variant="outlined"
          />
          <v-text-field
            v-model="email"
            density="comfortable"
            label="Email"
            rounded="xl"
            variant="outlined"
          />
          <v-text-field
            v-model="password"
            density="comfortable"
            label="Password"
            rounded="xl"
            type="password"
            variant="outlined"
          />
          <v-text-field
            v-model="passwordCopy"
            density="comfortable"
            label="Password (again)"
            rounded="xl"
            type="password"
            variant="outlined"
          />
        </form>
        <span v-if="error" class="ml-2 text-red-accent-1 text-caption">
          {{ error }}
        </span>
        <span v-if="authError && !error" class="ml-2 text-red-accent-1 text-caption">
          {{ authError }}
        </span>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0 justify-space-between">
        <v-btn color="primary" variant="text" @click="emit('switch-to-login')">
          Login instead
        </v-btn>
        <v-btn color="primary" :disabled="!!error" variant="flat" @click="emit('register', email, password, name)">
          Register
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
