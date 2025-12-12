<template>
  <v-app>
    <v-main>
      <router-view :key="$route.fullPath" />
    </v-main>
    <login-modal
      v-model="uiStore.isLoginOpen"
      @login="(email, password) => authStore.login({ email, password })"
      @switch-to-register="uiStore.openRegister"
    />
    <register-modal
      v-model="uiStore.isRegisterOpen"
      @register="(email, password, username) => authStore.register({ email, password, name:username })"
      @switch-to-login="uiStore.openLogin"
    />
    <are-you-sure-modal
      v-model="uiStore.isDeleteConfirmOpen"
      @confirm="threadStore.deleteCurrentThread()"
    />
  </v-app>
</template>

<script lang="ts" setup>
  import { watch } from 'vue'
  import { useAuthStore } from '@/stores/auth.ts'
  import { useThreadStore } from '@/stores/thread.ts'
  import { useUiStore } from '@/stores/ui.ts'

  const authStore = useAuthStore()
  const uiStore = useUiStore()
  const threadStore = useThreadStore()

  watch(() => authStore.isLoggedIn, value => value ? uiStore.closeModal() : uiStore.openLogin())
</script>
