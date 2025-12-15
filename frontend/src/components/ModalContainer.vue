<template>
  <login-modal
    v-model="uiStore.isLoginOpen"
    :auth-error="uiStore.loginError"
    @close="uiStore.clearErrors"
    @login="login"
    @switch-to-register="uiStore.openRegister"
  />
  <register-modal
    v-model="uiStore.isRegisterOpen"
    :auth-error="uiStore.registerError"
    @close="uiStore.clearErrors"
    @register="register"
    @switch-to-login="uiStore.openLogin"
  />
  <are-you-sure-modal
    v-model="uiStore.isDeleteConfirmOpen"
    @close="uiStore.clearErrors"
    @confirm="threadStore.deleteCurrentThread()"
  />
</template>

<script setup lang="ts">
  import { AxiosError } from 'axios'
  import { watch } from 'vue'
  import { useAuthStore } from '@/stores/auth.ts'
  import { useThreadStore } from '@/stores/thread.ts'
  import { useUiStore } from '@/stores/ui.ts'

  const authStore = useAuthStore()
  const uiStore = useUiStore()
  const threadStore = useThreadStore()

  async function login (email: string, password: string) {
    try {
      await authStore.login({ email, password })
      uiStore.clearErrors()
    } catch (error) {
      if (!(error instanceof AxiosError)) return
      if (!error?.status) return

      uiStore.loginError = [400, 422].includes(error.status) ? 'Invalid email or password.' : 'An unknown error occurred. Please try again.'
    }
  }

  async function register (email: string, password: string, username: string) {
    try {
      await authStore.register({ email, password, name: username })
      uiStore.clearErrors()
    } catch (error) {
      if (!(error instanceof AxiosError)) return
      if (!error?.status) return

      console.log(error)

      if (error?.status === 422) {
        uiStore.registerError = error?.response?.data?.detail
        return
      }

      uiStore.registerError = error?.status === 400 ? 'Email is already in use.' : 'An unknown error occurred. Please try again.'
    }
  }

  watch(() => authStore.isLoggedIn, value => value ? uiStore.closeModal() : uiStore.openLogin())
</script>
