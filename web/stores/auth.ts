import type { AuthCredentials, RegisterCredentials } from '@/entities/auth.ts'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { AuthRepo } from '@/repos/auth.ts'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  let refreshPromise: Promise<void> | null = null

  const isLoggedIn = computed(() => accessToken.value !== null)

  const refreshAccessToken = async () => {
    if (!refreshPromise) {
      refreshPromise = (async () => {
        try {
          const response = await AuthRepo.refreshToken()
          accessToken.value = response.data.token
        } catch (error) {
          accessToken.value = null
          throw error
        }
      })().finally(() => {
        refreshPromise = null
      })
    }
    return refreshPromise
  }

  const login = async (credentials: AuthCredentials) => {
    try {
      const response = await AuthRepo.login(credentials)
      accessToken.value = response.data.token
    } catch (error) {
      accessToken.value = null
      throw error
    }
  }

  const register = async (credentials: RegisterCredentials) => {
    try {
      const response = await AuthRepo.register(credentials)
      accessToken.value = response.data.token
    } catch (error) {
      accessToken.value = null
      throw error
    }
  }

  const logout = async () => {
    try {
      await AuthRepo.logout()
    } finally {
      accessToken.value = null
    }
  }

  return { accessToken, isLoggedIn, login, register, refreshAccessToken, logout }
})
