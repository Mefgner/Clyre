<script setup lang="ts">
  import { computed, ref } from 'vue'

  const email = ref('')
  const password = ref('')
  const name = ref('')
  const passwordCopy = ref('')
  const model = defineModel<boolean>({ default: false })

  const emit = defineEmits<{
    'register': [email: string, password: string, name: string]
    'switch-to-login': []
    'update:vModel': [isActive: boolean]
  }>()

  const isPasswordValid = computed(() => password.value === passwordCopy.value)
</script>

<template>
  <v-dialog v-model="model" max-width="400" persistent>
    <v-card elevation="12" rounded="xl">
      <v-card-title class="text-h5 font-weight-bold pa-4">
        Login to Clyre
      </v-card-title>
      <v-card-text>
        <v-text-field v-model="name" density="comfortable" label="Username" variant="outlined" />
        <v-text-field v-model="email" density="comfortable" label="Email" variant="outlined" />
        <v-text-field
          v-model="password"
          density="comfortable"
          label="Password"
          type="password"
          variant="outlined"
        />
        <v-text-field
          v-model="passwordCopy"
          density="comfortable"
          label="Password (again)"
          type="password"
          variant="outlined"
        />
      </v-card-text>

      <v-card-actions class="pa-4 pt-0 justify-space-between">
        <v-btn color="primary" variant="text" @click="emit('switch-to-login')">
          Login instead
        </v-btn>
        <v-btn color="primary" :disabled="!isPasswordValid" variant="flat" @click="emit('register', email, password, name)">
          Register
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
